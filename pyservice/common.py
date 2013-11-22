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


class ServiceException(Exception):
    '''Represents an error during Service operation'''
    default_message = "Internal Error"
    def __init__(self, *args):
        args = args or [self.default_message]
        super(ServiceException, self).__init__(*args)
