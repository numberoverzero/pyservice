import six
import json
import bottle

from pyservice.utils import (
    validate_name,
    parse_metadata,
    parse_name
)
from pyservice.common import (
    OP_ALREADY_REGISTERED,
    RESERVED_SERVICE_KEYS
)
from pyservice.operation import parse_operation, handle_request
from pyservice.layer import Stack


class Service(object):
    def __init__(self, name, **kwargs):
        validate_name(name)
        self.name = name
        self.operations = {}
        self.exceptions = []

        self._app = bottle.Bottle()
        @self._app.post("/{service}/<operation>".format(service=self.name))
        def handle(operation):
            # TODO: Update handler below to use registered serializers, and
            #         make this pass bottle.request.body
            #       route should probably be /api/service/<operation>/<protocol>
            #         and this function can delegate the call based on registered
            #         serializers
            return self.handle(operation, bottle.request.json)

        self._layers = []
        self._debug = False

    @classmethod
    def from_json(cls, data):
        return parse_service(data)

    @classmethod
    def from_file(cls, filename):
        with open(filename) as f:
            return Service.from_json(json.loads(f.read()))

    def _register_operation(self, name, operation):
        if name in self.operations:
            raise KeyError(OP_ALREADY_REGISTERED.format(name))
        self.operations[name] = operation

    def _register_exception(self, exception_cls):
        self.exceptions.append(exception_cls)

    def _register_layer(self, layer):
        self._layers.append(layer)

    @property
    def _stack(self):
        return Stack(self._layers[:])

    def operation(self, name=None, func=None, **kwargs):
        '''
        Return a decorator that maps an operation name to a function

        Both of the following are acceptable, and map to the operation "my_op":

        @service.operation("my_op")
        def func(arg):
            pass

        @service.operation
        def my_op(arg):
            pass
        '''
        wrap = lambda func: self.operations[name]._wrap(func, **kwargs)

        # @service
        # def name(arg):
        if callable(name):
            func, name = name, name.__name__
            name = func.__name__

        # service.operation("name", operation)
        if callable(func):
            return wrap(func)

        # @service.operation("name")
        else:
            # we need to return a decorator, since we don't have the function to decorate yet
            return wrap

    @property
    def _mapped(self):
        '''True if all operations have been mapped'''
        return all(op._mapped for op in six.itervalues(self.operations))

    @property
    def _config(self):
        '''Keep config centralized in bottle app'''
        return self._app.config

    def run(self, **kwargs):
        # Fail closed - assume production
        self._debug = kwargs.get("debug", self._debug)
        if not self._mapped:
            raise ValueError("Cannot run service without mapping all operations")
        self._app.run(**kwargs)

    def handle(self, op_name, body):
        # TODO: The entirety of operation.handle_request should be moved here.
        #       At the same time revisit operation._wrap to see if it can be cleaned up
        #       Serializers need to be hooked up here, and the bottle route in __init__
        #         needs to pass request.body instead of request.json
        try:
            operation = self.operations[op_name]
        except KeyError:
            bottle.abort(404, "Unknown operation {}".format(op_name))
        return handle_request(self, operation, operation._func, body)

def parse_service(data):
    service = Service(parse_name(data))
    for opdata in data.get("operations", []):
        parse_operation(service, opdata)
    parse_metadata(service, data, RESERVED_SERVICE_KEYS)
    return service
