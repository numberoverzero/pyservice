import six
import sys
import logging
import functools
from pyservice.exception_factory import ExceptionContainer
from pyservice.serialize import JsonSerializer
from pyservice.handlers import RequestsHandler
from pyservice.extension import execute
from pyservice.docstrings import docstring
from pyservice.util import filtered_copy
logger = logging.getLogger(__name__)


class _InternalClient(object):
    '''
    Does most of Client's heavy lifting - not part of the Client class because a
    Client dynamically binds operations to itself, and this minimizes the chance
    of a clash if operation naming restrictions are relaxed in the future (such
    as allowing leading underscores).
    '''
    def __init__(self, client, description, handler, serializer):
        self.external_client = client
        self.description = description
        self.handler = handler
        self.serializer = serializer

    def call(self, operation, **input):
        # Client sends input, meta to service
        # Service sends output, meta to client
        extensions = self.external_client.extensions[:] + [self]
        context = {
            "input": input,
            "meta": {},
            "output": {},
            "operation": operation,
            "extensions": extensions,
            "client": self
        }
        fire = functools.partial(execute, extensions, operation, context)

        try:
            fire("before_operation")
            fire("handle_operation")
            return filtered_copy(
                context["output"].items(),
                self.description.operations[operation].output
            )
        finally:
            fire("after_operation")

    def handle_operation(self, operation, context, next_handler):
        # dict -> wire
        data_out = self.serializer.serialize({
            "input": context["input"],
            "meta": context["meta"]
        })

        # wire -> wire
        try:
            response = self.handler.handle(
                self.description.name, operation, data_out)
        except Exception:
            msg = "Exception while handling operation '{}'' in service '{}'"
            logger.warn(msg.format(
                operation, self.description.name))
            raise

        # wire -> dict
        data_in = self.serializer.deserialize(response)
        if "output" in data_in:
            context["output"].update(data_in["output"])
        if "meta" in data_in:
            context["meta"].update(data_in["meta"])

        # Process exceptions in the handler
        # so surrounding extensions' handle_operation can try/catch
        self.handle_exception(operation, context)

        next_handler(context)

    def handle_exception(self, operation, context):
        '''
        Note that exception classes are generated from the external_client,
        since all consumers will be catching against external_client.exceptions.
        '''
        output = context["output"]
        exceptions = self.description.operations[operation].exceptions
        if "__exception" in output:
            ex_name = output["__exception"]["cls"]
            ex_args = output["__exception"]["args"]
            ex_cls = getattr(self.external_client.exceptions, ex_name)
            exception = ex_cls(*ex_args)

            if ex_name not in exceptions:
                # Exception was not in the list of declared exceptions for this
                # operation - wrap in service exception and raise
                wrap = self.external_client.exceptions.ServiceException
                exception = wrap(*[
                    "Unknown exception for operation {}".format(operation),
                    exception
                ])
            raise exception


@docstring
class Client(object):
    def __init__(self, description, handler, serializer):
        self.operations = {}
        self.exceptions = ExceptionContainer()
        self.extensions = []

        _client = _InternalClient(self, description, handler, serializer)
        bind_operations(self, _client, description.operations)

def bind_operations(client, internal_client, operations):
        # We need this nested function to create
        # a scope for the operation variable,
        # otherwise it gets the last value of the var
        # in the for loop it's under.
        for operation in operations:
            def make_call_op(operation):
                return lambda **input: internal_client.call(
                    operation, **input)
            func = make_call_op(operation)

            # Bind the operation function to the external client
            setattr(client, operation, func)
            client.operations[operation] = func

            #Register the operation with the internal client's handler
            internal_client.handler.register(
                internal_client.description.name,
                operation,
                internal_client
            )

class WebServiceClient(Client):
    '''Uses requests to make json calls to a web service'''
    def __init__(self, description):
        handler = RequestsHandler()
        serializer = JsonSerializer()
        super(WebServiceClient, self).__init__(description, handler, serializer)
