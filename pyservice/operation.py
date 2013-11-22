from pyservice.utils import (
    validate_name,
    parse_metadata,
    parse_name
)
from pyservice.common import (
    OP_ALREADY_MAPPED,
    BAD_FUNC_SIGNATURE,
    RESERVED_OPERATION_KEYS
)


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
        # TODO: See what's really needed here now that we're doing routing in the service
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

        # Return the function unchanged so that it can still be invoked normally
        return func

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
