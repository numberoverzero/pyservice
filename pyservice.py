import re
import six
import json
import bottle

RESERVED_SERVICE_KEYS = [
    "name",
    "operations"
]

RESERVED_OPERATION_KEYS = [
    "name",
    "input",
    "output"
]

OP_ALREADY_MAPPED = "Route has already been created for operation {}"
OP_ALREADY_REGISTERED = "Tried to register duplicate operation {}"
BAD_FUNC_SIGNATURE = "Invalid function signature: {}"

NAME_RE = re.compile("^[a-zA-Z]\w*$")

class ServiceException(Exception):
    '''Represents an error during Service operation'''
    pass

def validate_name(name):
    if not NAME_RE.search(name):
        raise ValueError("Invalid name: '{}'".format(name))

def parse_name(data):
    name = data["name"]
    validate_name(name)
    return name

def parse_operation(service, data):
    operation = Operation(service, parse_name(data))
    operation.input = data.get("input", [])
    operation.output = data.get("output", [])
    # Dump extra fields in metadta
    for key in data:
        if key not in RESERVED_OPERATION_KEYS:
            operation.metadata[key] = data[key]
    return operation

def parse_service(data):
    service = Service(parse_name(data))
    for opdata in data.get("operations", []):
        name = parse_name(opdata)
        parse_operation(service, opdata)
    # Dump extra fields in metadta
    for key in data:
        if key not in RESERVED_SERVICE_KEYS:
            service.metadata[key] = data[key]
    return service


class Operation(object):
    def __init__(self, service, name):
        validate_name(name)
        self.name = name
        self.service = service
        service.register(name, self)

        self.input = []
        self.output = []
        self.metadata = {}
        self.func = None

        # Build bottle route
        route = {
            'service': self.service.name,
            'operation': self.name
        }
        self.route = "/{service}/{operation}".format(**route)

    @property
    def mapped(self):
        '''True if this operation has been mapped to a function, including bottle routing'''
        return bool(self.func)

    def wrap(self, func, **kwargs):
        if self.func:
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

        self.func = func

        @self.service.app.post(self.route)
        def handle():
            input = self.build_input(bottle.request.json)
            output = self.func(*input)
            return self.build_output(output)

        # Return the function unchanged so that it can still be invoked normally
        return func

    def build_input(self, input):
        if set(input.keys()) != set(self.input):
            msg = "Input {} does not match required input {}"
            raise ServiceException(msg.format(input.keys(), self.input))
        if self.func is None:
            raise ServiceException("No wrapped function to order input args by!")
        return [input[varname] for varname in self.func.__code__.co_varnames]

    def build_output(self, output):
        if len(output) != 1:
            # Check for string/unicode
            is_string = isinstance(output, six.string_types)
            is_text = isinstance(output, six.text_type)
            if is_string or is_text:
                output = [output]

        if len(output) != len(self.output):
            msg = "Output {} does not match expected output format {}"
            raise ServiceException(msg.format(output, self.output))
        return {key: value for key, value in zip(self.output, output)}


class Service(object):
    def __init__(self, name):
        validate_name(name)
        self.name = name
        self.operations = {}
        self.app = bottle.Bottle()
        self.metadata = {}

    @classmethod
    def from_json(cls, data):
        return parse_service(data)

    @classmethod
    def from_file(cls, filename):
        with open(filename) as f:
            return Service.from_json(json.loads(f.read()))

    def register(self, name, operation):
        if name in self.operations:
            raise KeyError(OP_ALREADY_REGISTERED.format(name))
        self.operations[name] = operation

    def operation(self, name, **kwargs):
        '''Return a decorator that maps an operation name to a function'''
        return lambda func: self.operations[name].wrap(func, **kwargs)

    @property
    def mapped(self):
        '''True if all operations have been mapped'''
        return all(op.mapped for op in six.itervalues(self.operations))

    @property
    def config(self):
        '''Keep config centralized in bottle app'''
        return self.app.config

    def run(self, **kwargs):
        if not self.mapped:
            raise ValueError("Cannot run service without mapping all operations")
        self.app.run(**kwargs)
