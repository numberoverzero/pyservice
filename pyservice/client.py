import functools
import logging
from pyservice.exception_factory import ExceptionContainer
from pyservice.serialize import JsonSerializer
from pyservice.handlers import RequestsHandler
from pyservice.extension import execute
from pyservice.docstrings import docstring
from pyservice.util import filtered_copy
logger = logging.getLogger(__name__)


class _InternalClient(object):
    '''
    Does most of Client's heavy lifting - not part of the Client class because
    a Client dynamically binds operations to itself, and this minimizes the
    chance of a clash if operation naming restrictions are relaxed in the
    future (such as allowing leading underscores).
    '''
    def __init__(self, client, description, handler):
        self.external_client = client
        self.description = description
        self.handler = handler

    def call(self, operation, **request):
        extensions = self.external_client.extensions[:] + [self]
        context = {
            "__exception": {},
            "request": request,
            "response": {},

            # Meta about this operation
            "extensions": extensions,
            "operation": operation,
            "client": self.external_client  # External so extensions have
                                            # easy access to client.exceptions
        }
        fire = functools.partial(execute, extensions, operation, context)

        # The good stuff
        try:
            fire("before_operation")
            fire("handle_operation")
            return context["response"]
        finally:
            fire("after_operation")

    def handle_operation(self, operation, context, next_handler):
        try:
            response = self.handler.handle(
                self.description.name, operation, context["request"])
        except Exception:
            msg = "Exception while handling operation '{}'' in service '{}'"
            logger.warn(msg.format(
                operation, self.description.name))
            raise

        context["response"].update(response["response"])
        context["__exception"].update(response["__exception"])

        # Raise here so surrounding extensions can
        # try/catch in handle_operation
        if context["__exception"]:
            self.raise_exception(operation, context)

        next_handler(operation, context)

    def raise_exception(self, operation, context):
        '''
        Note that exception classes are generated from the external_client,
        since all consumers will be catching against
        external_client.exceptions.
        '''
        exception = context["__exception"]
        exceptions = self.description.operations[operation].exceptions

        name = exception["cls"]
        args = exception["args"]
        cls = getattr(self.external_client.exceptions, name)
        exception = cls(*args)

        if name not in exceptions:
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
    def __init__(self, description, handler):
        self.operations = {}
        self.exceptions = ExceptionContainer()
        self.extensions = []

        _client = _InternalClient(self, description, handler)
        bind_operations(self, _client, description.operations)

def bind_operations(client, internal_client, operations):
    # We need this nested function to create a scope for the operation
    # variable, otherwise it gets the last value of the var in the for
    # loop that it's under.
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
        serializer = JsonSerializer()
        handler = RequestsHandler(serializer)
        super(WebServiceClient, self).__init__(description, handler)
