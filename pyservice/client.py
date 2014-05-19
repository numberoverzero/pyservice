import requests
import functools
import logging
from .serialize import serializers
from .exception_factory import ExceptionContainer
from .extension import execute
from .docstrings import docstring
logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "protocol": "json",
    "timeout": 2,
    "strict" = True
}


def scrub_output(context, whitelist, strict=True):
    r = context.get("response", None)
    if r is None:
        context["response"] = {}
        return
    if not strict:
        return
    context["response"] = {r[k] for k in whitelist}


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

        self.external_client = client
        self.description = description
        self.serializer = serializers[self.config["protocol"]]

        # https://mysite.com/api/{protocol}/{version}/{operation}
        self.uri = self.description["endpoint"].format(
            protocol=self.config["protocol"],
            version=self.description["version"],
            operation="{operation}"  # Building a format string to use later
        )
        # Now self.uri is something like:
        # https://mysite.com/api/rpc/3.0/{operation}

    def call(self, operation, **request):
        '''Entry point from external client call'''
        extensions = self.external_client.extensions[:] + [self]
        context = {
            "exception": {},
            "request": request,
            "response": {},

            # Meta for this operation
            "extensions": extensions,
            "operation": operation,
            "description" self.description,
            "client": self.external_client  # External so extensions have
                                            # easy access to client.exceptions
        }
        fire = functools.partial(execute, extensions, operation, context)

        try:
            fire("before_operation")
            fire("handle_operation")
            return context["response"]
        finally:
            fire("after_operation")

            # After the after_operation event so we catch everything
            scrub_output(context,
                         self.description[operation].output,
                         strict=self.config.get("strict", True))

    def handle_operation(self, operation, context, next_handler):
        '''Invoked during fire("handle_operation")'''
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

        next_handler(operation, context)

    def raise_exception(self, operation, context):
        '''
        Exception classes are generated from the external_client,
        since all consumers will be catching against
        external_client.exceptions.
        '''
        exception = context["exception"]
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


@docstring
class Client(object):
    def __init__(self, description, **config):
        self.operations = {}
        self.exceptions = ExceptionContainer()
        self.extensions = []

        _client = _InternalClient(self, description, **config)
        bind_operations(self, _client, description.operations)
