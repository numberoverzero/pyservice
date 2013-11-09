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


class ServiceException(Exception):
    pass

def parse_name(data):
    return data["name"]

def parse_operation(service, operation, data):
    # Load opration input/output
    operation.input = data.get("input", [])
    operation.output = data.get("output", [])
    # Dump extra fields in metadta
    for key in data:
        if key not in RESERVED_OPERATION_KEYS:
            operation.metadata[key] = data[key]
    return operation

def parse_service(service, data):
    # Load up operations
    for opdata in data.get("operations", []):
        name = parse_name(opdata)
        operation = Operation(service, name)
        parse_operation(service, operation, opdata)
    # Dump extra fields in metadta
    for key in data:
        if key not in RESERVED_SERVICE_KEYS:
            service.metadata[key] = data[key]
    return service


class Operation(object):
    def __init__(self, service, name):
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

        def handle():
            # Load request body,
            # Build func args from request body
            #  + service description defaults
            inp = bottle.request.json
            inp = self.build_input(inp)

            # Invoke function
            out = self.func(*inp)

            # Build return values,
            # Return output as json
            out = self.build_output(out)
            return json.dumps(out)

        wrapper = self.service.app.post(self.route)
        handle = wrapper(handle)
        self.func = func

        return handle

    def build_input(self, inp):
        if set(inp.keys()) != set(self.input):
            msg = "Input {} does not match required input {}"
            raise ServiceException(msg.format(inp.keys(), self.input))

    def build_output(self, out):
        if set(out.keys()) != set(self.output):
            msg = "Output {} does not match expected output {}"
            raise ServiceException(msg.format(out.keys(), self.output))


class Service(object):
    def __init__(self, name):
        self.name = name
        self.operations = {}
        self.app = bottle.Bottle()
        self.metadata = {}

    @classmethod
    def from_json(cls, data):
        name = parse_name(data)
        service = Service(name)
        return parse_service(service, data)

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
