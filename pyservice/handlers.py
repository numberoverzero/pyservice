import bottle
import functools
from .serialize import serializers


def to_wire(protocol, data):
    return serializers[protocol]['serialize'](data)


def from_wire(protocol, string):
    return serializers[protocol]['deserialize'](string)


class BottleHandler(ServiceHandler):  # pragma: no cover
    DEFAULT_OPTIONS = {
        "debug": False
    }

    def __init__(self, **kwargs):
        import bottle
        self.serializers = {}
        self.kwargs = dict(BottleHandler.DEFAULT_OPTIONS)
        self.kwargs.update(kwargs)
        self.app = bottle.Bottle()

    def route(self, service, description):
        '''
        service is a pyservice.Service.  Build a URI pattern from description
        that bottle will route to service.call(operation, request)
        '''
        pattern = "/api/<service>/<version>/<operation>".format
        self.app.post(pattern)(functools.partial(self.call, service))

    def call(self, service, operation):
        '''
        Bottle entry point -
            service is a `pyservice.Service`
            operation is a string of the operation to invoke
        '''
        if operation not in service.description.operations:
            bottle.abort(404, "Unknown Operation")

        try:
            # Read request
            body = bottle.request.body.read().decode("utf-8")
            wire_in = self.serializer.deserialize(body)

            # Process
            request = wire_in["request"]
            response = service.call(operation, request)

            # Write response
            wire_out = self.serializer.serialize({
                "response": response.get("response", {}),
                "__exception": response.get("__exception", {})
            })
            return wire_out
        except Exception:
            bottle.abort(500, "Internal Error")

    def run(self, *args, **kwargs):
        self.kwargs.update(kwargs)
        self.app.run(*args, **self.kwargs)
