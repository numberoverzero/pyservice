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

    def __init__(self, client, description):
        self.ext_client = client
        self.description = description
        self.serializer = serializers[self.config["protocol"]]
        self.fire = None

        # https://mysite.com/api/{protocol}/{version}/{operation}
        uri = self.description
        self.uri = "{scheme}://{host}:{port}{path}".format(
            **self.description.endpoint
        )
        self.uri = self.uri.format(
            protocol=self.config["protocol"],
            version=self.description.version,
            operation="{operation}"  # Building a format string to use later
        )
        logger.info("Service uri is {}".format(self.uri))

    @property
    def config(self):
        return self.ext_client.config

    @property
    def extensions(self):
        return self.ext_client.extensions

    @property
    def exceptions(self):
        return self.ext_client.exceptions

    def call(self, operation, request):
        '''Entry point from external client call'''
        if not self.fire:
            self.fire = chain(self.extensions[:] + [self], "handle")

        logger.info("call(operation={o}, request={r})".format(
            o=operation, r=request))
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
                context, self.description.operations[operation].output,
                strict=self.config.get("strict", True))

    def handle(self, next_handler, event, operation, context):
        logger.debug("handle(event={event}, context={context})".format(
            event=event, context=context))
        if event == "operation":
            try:
                wire_out = self.serializer.serialize(
                    {"request": context["request"]})
                wire_in = requests.post(
                    self.uri.format(operation=operation),
                    data=wire_out, timeout=self.config["timeout"])
                wire_in.raise_for_status()
                r = self.serializer.deserialize(wire_in.text)
                for key in ["response", "exception"]:
                    context[key].update(r.get(key, {}))
            except Exception as exception:
                msg = "Exception during operation {}".format(operation)
                logger.exception(msg, exc_info=exception)
                raise

            if context["exception"]:
                # Raise here so surrounding extensions can try/catch
                self.raise_exception(operation, context)
            else:
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
        cls = getattr(self.exceptions, name)
        exception = cls(*args)

        whitelisted = name in exceptions
        debugging = self.config.get("debug", False)
        logging.debug("raise_exception(whitelist={w}, debugging={d})".format(
            w=whitelisted, d=debugging))

        if not (whitelisted or debugging):
            # Not debugging and not an expected exception,
            # wrap so it doesn't bubble up
            wrap = self.exceptions.ServiceException
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
        self.config = dict(DEFAULT_CONFIG)
        self.config.update(config)

        _client = _InternalClient(self, description)
        bind_operations(self, _client, description.operations)
