import bottle
from pyservice.common import ServiceException
from pyservice.layer import Stack
from pyservice import utils

def handle(service, operation, body, serializer):
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
        try:
            context["exception"] = exception
            validate_exception(context)
        except ValueError:
            # Blow away the exception if validation fails
            context["exception"] = ServiceException()
        finally:
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

def validate_input(context):
    '''Make sure input has at least the required fields for mapping to a function'''
    json_input = set(context["input"])
    op_args = set(context["operation"].input)
    if not json_input.issuperset(op_args):
        msg = 'Input "{}" does not contain required params "{}"'
        raise ValueError(msg.format(context["input"], op_args))
    if context["operation"]._func is None:
        raise ValueError("No wrapped function to order input args by!")

def validate_output(context):
    '''Make sure the expected fields are present in the output'''
    json_output = set(context["output"])
    op_returns = set(context["operation"].output)
    if not json_output.issuperset(op_returns):
        msg = 'Output "{}" does not contain required values "{}"'
        raise ValueError(msg.format(context["output"], op_returns))

def validate_exception(context):
    '''Make sure the exception returned is whitelisted - otherwise throw a generic InteralException'''
    exception = context["exception"]
    service = context["service"]

    whitelisted = exception.__class__ in service.exceptions
    debugging = service._debug

    if not whitelisted and not debugging:
        raise ValueError("'{}' Exceptions are not whitelisted".format(exception.__class__))

class FunctionExecutor(object):
    def __init__(self, operation, func):
        self.operation = operation
        self.func = func

    def handle_request(self, context, next):
        dict_ = context["input"]
        signature = self.operation._argnames
        args = utils.to_list(dict_, signature)

        result = self.func(*args)

        signature = self.operation.output
        dict_ = utils.to_dict(result, signature)
        context["output"].update(dict_)

        next.handle_request(context)
