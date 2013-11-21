import bottle
from pyservice.serialize import JsonSerializer
from pyservice.utils import (
    validate_input,
    validate_output,
    validate_exception
)
from pyservice.layer import Stack

def handle(service, operation, body):
    # TODO: hardcoding json serializer for now
    # This should be an arg passed into handle
    serializer = JsonSerializer()

    try:
        context = {
            "input": serializer.deserialize(body),
            "output": {},
            "service": service,
            "operation": operation
        }
        stack = Stack(service._layers[:])
        stack.append(FunctionExecutor(operation, operation._func))
        stack.handle_request(context)

        validate_output(context)
        result = context["output"]
        return serializer.serialize(result)
    except Exception as exception:
        context["exception"] = exception
        validate_exception(context)
        exception = context["exception"]
        result = {
            "__exception": {
                'cls': exception.__class__.__name__,
                'args': exception.args
            }
        }
        try:
            return serializer.serialize(result)
        except Exception:
            bottle.abort(500, "Internal Error")


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
        # TODO: This needs to be refactored to a common location
        #       so that Client can use it for unpacking operation output
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
