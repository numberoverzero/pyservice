import functools


class ClientHandler(object):  # pragma: no cover
    '''
    Should handle 404, 500
    '''
    def register(self, service_name, operation, **kwargs):
        pass
    def handle(self, service_name, operation, request):
        pass


class ServiceHandler(object):  # pragma: no cover
    '''
    Can return 404, 500
    '''
    def route(self, service, pattern):
        '''
        Instruct the handler to delegate any request whose URI matches
        `pattern` to the `service` to construct a response
        '''
        pass
    def run(self, *args, **kwargs):
        pass


class RequestsHandler(ClientHandler):
    URI = "{schema}://{host}:{port}/{service}/{{operation}}"
    DEFAULT_OPTIONS = {
        "schema": "https",
        "host": "localhost",
        "port": "8080",
        "timeout": 5
    }

    def __init__(self, serializer, **kwargs):
        import requests
        self.serializer = serializer
        self.kwargs = dict(RequestsHandler.DEFAULT_OPTIONS)
        self.kwargs.update(kwargs)
        self.uris = {}

    def register(self, service_name, operation, **kwargs):
        kwargs = dict(self.kwargs)
        kwargs.update(kwargs)

        key = (service_name, operation)
        uri = RequestsHandler.URI.format(
            schema = kwargs["schema"],
            host = kwargs["host"],
            port = kwargs["port"],
            service = service_name,
            operation = operation
        )

        timeout = kwargs["timeout"]
        self.uris[key] = (uri, timeout)

    def handle(self, service_name, operation, request):  # pragma: no cover
        # Serialize request for wire
        wire_out = self.serializer.serialize({"request": request})

        # Load endpoint
        key = (service_name, operation)
        uri, timeout = self.uris[key]

        # Wire request
        wire_in = requests.post(uri, data=wire_out, timeout=timeout)

        # TODO: Handle 404/500 here
        #  response.raise_for_status()

        # Deserialize response from wire
        response = self.serializer.deserialize(wire_in.text)

        # Always provide response, __exception values
        return {
            "response": response.get("response", {}),
            "__exception": response.get("__exception", {})
        }


class BottleHandler(ServiceHandler):  # pragma: no cover
    DEFAULT_OPTIONS = {
        "debug": False
    }

    def __init__(self, serializer, **kwargs):
        import bottle
        self.serializer = serializer
        self.kwargs = dict(BottleHandler.DEFAULT_OPTIONS)
        self.kwargs.update(kwargs)
        self.app = bottle.Bottle()

    def route(self, service, pattern):
        '''
        service is a pyservice.Service.  Any request URI that matches `pattern`
        will invoke service.call(operation, request)
        '''
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
