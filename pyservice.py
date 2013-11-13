import re
import six
import json
import bottle
import functools

EVENTS = [
    "on_input",
    "on_output",
    "on_exception"
]

RESERVED_SERVICE_KEYS = [
    "exceptions",
    "name",
    "operation",
    "operations",
    "raise_",
    "run",
]

RESERVED_OPERATION_KEYS = [
    "exceptions",
    "input",
    "name",
    "output",
]

OP_ALREADY_MAPPED = "Route has already been created for operation {}"
OP_ALREADY_REGISTERED = "Tried to register duplicate operation {}"
EX_ALREADY_REGISTERED = "Tried to register duplicate exception {}"
BAD_FUNC_SIGNATURE = "Invalid function signature: {}"

# Most names can only be \w*,
# with the special restriction that the
# first character must be a letter
NAME_RE = re.compile("^[a-zA-Z]\w*$")

def validate_name(name):
    if not NAME_RE.search(name):
        raise ValueError("Invalid name: '{}'".format(name))

def parse_name(data):
    name = data["name"]
    validate_name(name)
    return name

def parse_metadata(obj, data, blacklist):
    for key, value in six.iteritems(data):
        validate_name(key)
        if key not in blacklist:
            setattr(obj, key, value)

def parse_operation(service, data):
    operation = Operation(service, parse_name(data))
    for attr in ["input", "output", "exceptions"]:
        value = data.get(attr, [])
        # Validate all fields
        map(validate_name, value)
        setattr(operation, attr, value)
    parse_metadata(operation, data, RESERVED_OPERATION_KEYS)
    return operation

def parse_service(data):
    service = Service(parse_name(data))
    for opdata in data.get("operations", []):
        name = parse_name(opdata)
        parse_operation(service, opdata)
    parse_metadata(service, data, RESERVED_SERVICE_KEYS)
    return service

def handle_request(service, operation, func):
    context = {
        "input": bottle.request.json,
        "service": service,
        "operation": operation
    }
    try:
        # Set up input args
        service._invoke_event("on_input", context)
        data = context["input"]
        args = [data[argname] for argname in operation._argnames]

        context["result"] = func(*args)
        context["output"] = {}
        service._invoke_event("on_output", context)

        # Return built up json
        return context["output"]

    except Exception as e:
        context["_e"] = e
        context["exception"] = {}
        service._invoke_event("on_exception", context)
        return context["exception"]


class Operation(object):
    def __init__(self, service, name):
        validate_name(name)
        self.name = name
        self._service = service
        service._register_operation(name, self)

        self.input = []
        self.output = []
        self._func = None

        # Build bottle route
        route = {
            'service': self._service.name,
            'operation': self.name
        }
        self._route = "/{service}/{operation}".format(**route)

    @property
    def _mapped(self):
        '''True if this operation has been mapped to a function, including bottle routing'''
        return bool(self._func)

    @property
    def _argnames(self):
        return self._func.__code__.co_varnames

    def _wrap(self, func, **kwargs):
        if self._func:
            raise ValueError(OP_ALREADY_MAPPED.format(self.name))

        # Function signature cannot include *args or **kwargs
        varnames = func.__code__.co_varnames
        argcount = func.__code__.co_argcount
        if len(varnames) != argcount:
            msg = "Contains *args or **kwargs"
            raise ValueError(BAD_FUNC_SIGNATURE.format(msg))

        # Args must be an exact match
        if set(varnames) != set(self.input):
            msg = "Does not match operation description"
            raise ValueError(BAD_FUNC_SIGNATURE.format(msg))

        self._func = func

        handler = lambda: handle_request(self._service, self, func)
        self._service._app.post(self._route)(handler)
        # Return the function unchanged so that it can still be invoked normally
        return func


class Service(object):
    def __init__(self, name, **kwargs):
        validate_name(name)
        self.name = name
        self.operations = {}
        self.exceptions = {}
        self._app = bottle.Bottle()
        self._handlers = {event:[] for event in EVENTS}

        # Exceptions
        register_base_exceptions = kwargs.pop("use_base_exceptions", True)
        _base_exceptions = [
            ("ServiceException", ServiceException),
            ("ServerException", ServerException),
            ("ClientException", ClientException)
        ]
        if register_base_exceptions:
            for name, exception_cls in _base_exceptions:
                self._register_exception(name, exception_cls)

        # Layer
        register_base_layer = kwargs.pop("use_base_layer", True)
        _base_layer = [
            BasicValidationLayer
        ]
        if register_base_layer:
            for layer in _base_layer:
                layer(self, **kwargs)

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

    def _register_exception(self, name, exception_cls):
        if name in self.exceptions:
            raise KeyError(EX_ALREADY_REGISTERED.format(name))
        self.exceptions[name] = exception_cls

    def _register_layer(self, layer):
        for event in EVENTS:
            handler = getattr(layer, event, None)
            if handler:
                self._handlers[event].append(handler)

    def _invoke_event(self, event, context):
        '''
        Sample request invocation:
            Logging.on_input ----> Caching.on_input ----> Service.on_input ----> |
                                                                                 |
            Logging.on_output <--- Session.on_output <--- Service.on_output <-- <-

        In the sample above Logging was added last.  To accomplish the ordering above,
            walk input handlers in reverse, and output/exception handlers forward
        '''

        handlers = self._handlers.get(event, None)
        if handlers is None:
            raise ServerException("Unknown event {} invoked.".format(event))

        if event == "on_input":
            handlers = reversed(handlers)

        for handler in handlers:
            handler(context)

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

    def raise_(self, name, message=''):
        '''
        Raise an exception registered with the service

        If no exception with the given name is registered,
        raises a generic ServerException
        '''
        exception = self.exceptions.get(name, None)
        if not exception:
            raise ServerException()
        raise exception(message)

    def run(self, **kwargs):
        # Fail closed - assume production
        self._debug = kwargs.get("debug", False)
        if not self._mapped:
            raise ValueError("Cannot run service without mapping all operations")
        self._app.run(**kwargs)


class ServiceException(Exception):
    '''Represents an error during Service operation'''
    pass

class ServerException(ServiceException):
    '''The server did something wrong'''
    default_message = "Internal Error"
    def __init__(self, message=None, **kwargs):
        message = message or ServerException.default_message
        super(ServerException, self).__init__(message, **kwargs)

class ClientException(ServiceException):
    '''The client did something wrong'''
    pass

class Layer(object):
    def __init__(self, service=None, **kwargs):
        if service:
            service._register_layer(self)

class BasicValidationLayer(Layer):
    def on_input(self, context):
        json_input = context["input"]
        op_args = context["operation"].input
        if set(json_input.keys()) != set(op_args):
            msg = "Input {} does not match required input {}"
            raise ClientException(msg.format(json_input.keys(), op_args))
        if context["operation"]._func is None:
            raise ServerException("No wrapped function to order input args by!")

    def on_output(self, context):
        func_result = context["result"]
        json_output = context["output"]
        expected_result = context["operation"].output

        msg = "Output {} does not match expected output format {}"
        exception = ServerException(msg.format(func_result, expected_result))

        # No output expected
        if len(expected_result) == 0:
            if func_result is not None:
                raise exception
            else:
                return

        # One value - optimistically assume that even if
        # something has an __iter__ method, it
        # represents one value (such as strings)
        if len(expected_result) == 1:
            json_output[expected_result[0]] = func_result

        # Multiple values - verify length and map
        # expected_result keys to func_result values
        else:
            if len(expected_result) != len(func_result):
                raise exception
            for key, value in zip(expected_result, func_result):
                func_result[key] = value

    def on_exception(self, context):
        # Whitelist on registered service exceptions
        # anything else gets a general "Exception" and dummy message
        _e = context["_e"]
        whitelisted_exceptions = context["service"].exceptions
        whitelisted = _e.__class__ in whitelisted_exceptions
        debugging = context["service"]._debug

        if not whitelisted and not debugging:
            # Blow away the exception
            _e = context["_e"] = ServerException()

        context["exception"] = {
            "_exception": {
                "cls": _e.__class__.__name__,
                "message": _e.message
            }
        }
