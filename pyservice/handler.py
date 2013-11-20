from pyservice.serialize import JsonSerializer
from pyservice.utils import (
    validate_input,
    validate_output,
    validate_exception
)

def handle(service, operation, body):
    # Move logic in handle_request to this method
    # (or helpers)

    # TODO: hadcoding json serializer for now
    # This should be an arg passed into handle
    serializer = JsonSerializer()

    string_in = body
    dict_in = serializer.deserialize(string_in, strict=False)
    dict_out = _handle(service, operation, operation._func, dict_in)
    string_out = serializer.deserialize(dict_out)
    return string_out

def _handle(service, operation, func, input):
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

class FunctionExecutor(object):
    def __init__(self, operation, func):
        self.operation = operation
        self.func = func

    def handle_request(self, context, next):
        validate_input(context)
        data = context["input"]
        args = [data[argname] for argname in self.operation._argnames]

        result = self.func(*args)
        self.map_output(result, context)
        next.handle_request(context)

    def map_output(self, result, context):
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
