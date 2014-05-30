import requests
import logging
from .serialize import serializers
from .exception_factory import ExceptionContainer
from .chain import chain
from .docstrings import docstring
from .common import DEFAULT_CONFIG, scrub_output
logger = logging.getLogger(__name__)


class _InternalClient(object):
    '''
    Does most of Client's heavy lifting - not part of the Client class because
    a Client dynamically binds operations to itself, and this minimizes the
    chance of a clash if operation naming restrictions are relaxed in the
    future (such as allowing leading underscores).
    '''

    def __init__(self, client, description, **config):
        self.config = dict(DEFAULT_CONFIG)
        self.config.update(config)

        self.ext_client = client
        self.description = description
        self.serializer = serializers[self.config["protocol"]]
        self.fire = None

        # https://mysite.com/api/{protocol}/{version}/{operation}
        self.uri = self.description["endpoint"].format(
            protocol=self.config["protocol"],
            version=self.description["version"],
            operation="{operation}"  # Building a format string to use later
        )

    def call(self, operation, request):
        '''Entry point from external client call'''
        if not self.fire:
            self.fire = chain(self.ext_client.extensions[:] + [self])
        context = {
            "exception": {},
            "request": request,
            "response": {},

            # Meta for this operation
            "operation": operation,
            "description": self.description,
            "client": self.ext_client  # External so extensions have
                                       # easy access to client.exceptions
        }

        try:
            self.fire("before_operation", operation, context)
            self.fire("operation", operation, context)
            return context["response"]
        finally:
            self.fire("after_operation", operation, context)

            # After the after_operation event so we catch everything
            # This will occur before the return above, so we can still
            # clean things up before they get back to the caller
            scrub_output(
                context, self.description[operation].output,
                strict=self.config.get("strict", True))

    def handle(self, next_handler, event, operation, context):
        if event == "operation":
            try:
                wire_out = self.serializer.serialize({"request": request})
                wire_in = requests.post(
                    self.uri.format(operation=operation),
                    data=wire_out, timeout=self.config["timeout"])
                response = self.serializer.deserialize(wire_in)
                response = {
                    "response": response.get("response", {}),
                    "exception": response.get("exception", {})
                }
            except Exception:
                msg = "Exception while handling operation '{}'' in service '{}'"
                logger.warn(msg.format(
                    operation, self.description.name))
                raise

            context["response"].update(response["response"])
            context["exception"].update(response["exception"])

            # Raise here so surrounding extensions can
            # try/catch in handle_operation
            if context["exception"]:
                self.raise_exception(operation, context)
            next_handler(event, operation, context)
        else:
            # Pass through
            next_handler(event, operation, context)

    def raise_exception(self, operation, context):
        '''
        Exception classes are generated from the external client,
        since all consumers will be catching against
        external client.exceptions.
        '''
        exception = context["exception"]
        exceptions = self.description.operations[operation].exceptions

        name = exception["cls"]
        args = exception["args"]
        cls = getattr(self.ext_client.exceptions, name)
        exception = cls(*args)

        if name not in exceptions:
            # Exception was not in the list of declared exceptions for this
            # operation - wrap in service exception and raise
            wrap = self.ext_client.exceptions.ServiceException
            exception = wrap(*[
                "Unknown exception for operation {}".format(operation),
                exception
            ])
        raise exception


def bind_operations(client, internal_client, operations):
    # We need this nested function to create a scope for the operation
    # variable, otherwise it gets the last value of the var in the for
    # loop that it's under.
    for operation in operations:
        def make_call_op(operation):
            return lambda **request: internal_client.call(operation, request)
        func = make_call_op(operation)

        # Bind the operation function to the external client
        setattr(client, operation, func)
        client.operations[operation] = func


@docstring
class Client(object):
    def __init__(self, description, **config):
        self.operations = {}
        self.exceptions = ExceptionContainer()
        self.extensions = []

        _client = _InternalClient(self, description, **config)
        bind_operations(self, _client, description.operations)
