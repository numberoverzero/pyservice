import re
import six
import json
import bottle

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
BAD_FUNC_SIGNATURE = "Invalid function signature: {}"

# Most names can only be \w*,
# with the special restriction that the
# first character must be a letter
NAME_RE = re.compile("^[a-zA-Z]\w*$")

def validate_name(name):
    if not NAME_RE.search(name):
        raise ValueError("Invalid name: '{}'".format(name))

def validate_input(context):
    '''Make sure input has at least the required fields for mapping to a function'''
    json_input = set(context["input"])
    op_args = set(context["operation"].input)
    if not json_input.issuperset(op_args):
        msg = 'Input "{}" does not contain required params "{}"'
        raise ServiceException(msg.format(context["input"], op_args))
    if context["operation"]._func is None:
        raise ServiceException("No wrapped function to order input args by!")

def validate_output(context):
    '''Make sure the expected fields are present in the output'''
    json_output = set(context["output"])
    op_returns = set(context["operation"].output)
    if not json_output.issuperset(op_returns):
        msg = 'Output "{}" does not contain required values "{}"'
        raise ServiceException(msg.format(context["output"], op_returns))

def validate_exception(context):
    '''Make sure the exception returned is whitelisted - otherwise throw a generic InteralException'''
    exception = context["__exception"]
    service = context["service"]

    whitelisted = exception.__class__ in service.exceptions
    debugging = service._debug

    if not whitelisted and not debugging:
        # Blow away the exception
        context["__exception"] = ServiceException()

def map_output(result, context):
    '''
    Using the operation's description, map result fields to
    context["output"]
    '''
    output_keys = context["operation"].output

    # No output expected
    if len(output_keys) == 0:
        return

    # One value - assume that even objs with an __iter__
    # method represent one value (such as strings)
    if len(output_keys) == 1:
        result = [result]

    # Multiple values
    # We don't raise on unequal lengths, in case there's some
    # weird post-processing going on
    for key, value in zip(output_keys, result):
        context["output"][key] = value

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
    def attr(name):
        value = data.get(name, [])
        map(validate_name, value)
        return value

    name = parse_name(data)
    input = attr("input")
    output = attr("output")

    operation = Operation(service, name, input, output)
    parse_metadata(operation, data, RESERVED_OPERATION_KEYS)
    return operation

def parse_service(data):
    service = Service(parse_name(data))
    for opdata in data.get("operations", []):
        parse_operation(service, opdata)
    parse_metadata(service, data, RESERVED_SERVICE_KEYS)
    return service

def handle_request(service, operation, func, input):
    context = {
        "input": input,
        "output": {},
        "service": service,
        "operation": operation
    }
    try:
        # Set up layers, including real execution pseudo-layer
        stack = service._stack
        stack.append(FunctionExecutor(operation, func))
        stack.handle_request(context)

        validate_output(context)
        return context["output"]

    except Exception as exception:
        context["__exception"] = exception
        validate_exception(context)
        exception = context["__exception"]
        return {
            "__exception": {
                'cls': exception.__class__.__name__,
                'args': exception.args
            }
        }


class Operation(object):
    def __init__(self, service, name, input, output):
        validate_name(name)
        self.name = name
        self._service = service
        service._register_operation(name, self)

        self.input = input
        self.output = output
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
            msg = 'Does not match operation description: "{}" "{}"'.format(varnames, self.input)
            raise ValueError(BAD_FUNC_SIGNATURE.format(msg))

        self._func = func

        handler = lambda: handle_request(self._service, self, func, bottle.request.json)
        self._service._app.post(self._route)(handler)
        # Return the function unchanged so that it can still be invoked normally
        return func


class Service(object):
    def __init__(self, name, **kwargs):
        validate_name(name)
        self.name = name
        self.operations = {}
        self.exceptions = []
        self._app = bottle.Bottle()
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


class ServiceException(Exception):
    '''Represents an error during Service operation'''
    default_message = "Internal Error"
    def __init__(self, *args):
        args = args or [self.default_message]
        super(ServiceException, self).__init__(*args)


class Layer(object):
    def __init__(self, service=None, **kwargs):
        if service:
            service._register_layer(self)
    def handle_request(self, context, next):
        # Do some pre-request work

        # Have the next layer process the request
        next.handle_request(context)

        # Do some post-request work


class Stack(object):
    def __init__(self, layers=None):
        self.layers = layers or []
        self.index = 0

    def append(self, layer):
        self.layers.append(layer)

    def extend(self, iterable):
        self.layers.extend(iterable)

    def handle_request(self, context):
        # End of the chain
        if self.index >= len(self.layers):
            return
        layer = self.layers[self.index]
        self.index += 1
        layer.handle_request(context, self)


class FunctionExecutor(object):
    def __init__(self, operation, func):
        self.operation = operation
        self.func = func

    def handle_request(self, context, next):
        validate_input(context)
        data = context["input"]
        args = [data[argname] for argname in self.operation._argnames]

        result = self.func(*args)
        map_output(result, context)
        next.handle_request(context)

