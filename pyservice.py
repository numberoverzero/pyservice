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
    "name",
    "operations",
    "exceptions",
    "operation",
    "raise_",
    "run"
]

RESERVED_OPERATION_KEYS = [
    "name",
    "input",
    "output",
    "exceptions",
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

        @self._service._app.post(self._route)
        def handle():
            try:
                input = self._build_input(bottle.request.json)
                output = self._func(*input)
                return self._build_output(output)
            # Don't catch bottle exceptions, such as HTTPError
            # Otherwise stack traces during debugging are lost
            except bottle.BottleException:
                raise
            except Exception as e:
                return build_exception(e)

        # Return the function unchanged so that it can still be invoked normally
        return func

    def _build_input(self, input):
        if set(input.keys()) != set(self.input):
            msg = "Input {} does not match required input {}"
            raise ClientException(msg.format(input.keys(), self.input))
        if self._func is None:
            raise ServerException("No wrapped function to order input args by!")
        return [input[varname] for varname in self._func.__code__.co_varnames]

    def _build_output(self, output):
        if len(output) != 1:
            # Check for string/unicode
            is_string = isinstance(output, six.string_types)
            is_text = isinstance(output, six.text_type)
            if is_string or is_text:
                output = [output]

        if len(output) != len(self.output):
            msg = "Output {} does not match expected output format {}"
            raise ServerException(msg.format(output, self.output))
        return {key: value for key, value in zip(self.output, output)}

    def _build_exception(self, exception):
        # Whitelist on registered service exceptions
        # anything else gets a general "Exception" and dummy message
        whitelisted = exception.__class__ in self._service.exceptions
        debugging = self._service.debug
        if not whitelisted and not debugging:
            exception = ServerException()

        return {
            "_exception": {
                "cls": exception.__class__,
                "message": exception.message
            }
        }


class Service(object):
    def __init__(self, name):
        validate_name(name)
        self.name = name
        self.operations = {}
        self.exceptions = {}
        self._app = bottle.Bottle()

        _base_exceptions = [
            ("ServiceException", ServiceException),
            ("ServerException", ServerException),
            ("ClientException", ClientException)
        ]
        for name, exception_cls in _base_exceptions:
            self._register_exception(name, exception_cls)

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
