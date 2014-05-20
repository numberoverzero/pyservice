import bottle
import functools
import logging
from .common import DEFAULT_CONFIG, scrub_output
from .exception_factory import ExceptionContainer
from .serialize import serializers
from .extension import extension_chain
from .docstrings import docstring
logger = logging.getLogger(__name__)


@docstring
class Service(object):
    def __init__(self, description, **config):
        self.config = dict(DEFAULT_CONFIG)
        self.config.update(config)

        self.exceptions = ExceptionContainer()
        self.description = description
        self.extensions = []
        self.functions = {}
        self.chain = None

        # Building a bottle routing format
        # https://mysite.com/api/{protocol}/{version}/{operation}
        self.uri = self.description["endpoint"].format(
            protocol="<protocol>",
            version="<version>",
            operation="<operation>"
        )

        self.app = bottle.Bottle()
        self.app.post(self.uri)(self.call)
        self.serializer = serializers[self.config["protocol"]]

    def run(self, *args, **config):
        # Snapshot the set of extensions when the service starts
        self.chain = extension_chain(self.extensions[:] + [self])

        run_config = dict(self.config)
        run_config.update(config)
        self.app.run(*args, **run_config)

    def operation(self, func, name=None):
        # func isn't a func, it's the operation name
        if not callable(func):
            return functools.partial(self.operation, name=func)

        if name not in self.description.operations:
            raise ValueError("Unknown operation: " + name)

        self.functions[name] = func
        return func

    def call(self, protcol, version, operation):
        '''Entry point from bottle'''
        if protocol != self.config["protocol"]:
            bottle.abort(400, "Unsupported protocol: " + protocol)
        if version != self.description["version"]:
            bottle.abort(400, "Unsupported version: " + version)
        if operation not in self.description.operations:
            bottle.abort(404, "Unknown operation: " + operation)

        context = {
            "exception": {},
            "request": {},
            "response": {},

            # Meta for this operation
            "operation": operation,
            "description": self.description,
            "service": self
        }

        try:
            self.chain.before_operation(operation, context)

            # Read request
            wire_in = bottle.request.body.read().decode("utf-8")
            request = self.serializer.deserialize(wire_in)
            context["request"] = request.get("request", {})

            # Process
            self.chain.handle_operation(operation, context)

            # Note that copy/sanitize happens before the after handlers.
            # This is so that the response can safely access
            # extension-dependent values, such as objects from a sqlalchemy
            # session.  Once the response is serialized, the after hook can
            # do whatever it wants.

            # Make a copy of the response/exception so we can scrub
            out = {
                "response": context.get("response", {}),
                "exception": context.get("exception", {})
            }
            scrub_output(
                out, self.description[operation].output,
                strict=self.config.get("strict", True))

            # Write response
            wire_out = self.serializer.serialize(out)
            return wire_out
        except Exception:
            bottle.abort(500, "Internal Error")
        finally:
            self.chain.after_operation(operation, context)

    def handle_operation(self, operation, context, next_handler):
        try:
            self.functions[operation](context["request"], context["response"])
            next_handler(operation, context)
        except Exception as exception:
            self.raise_exception(self, operation, exception, context)

    def raise_exception(self, operation, exception, context):
        cls = exception.__class__.__name__
        args = exception.args

        whitelisted = cls in self.description.operations[operation].exceptions
        debugging = self.config.get("debug", False)
        if not (whitelisted or debugging):
            cls = "ServiceException"
            args = ["Internal Error"]

        context["exception"] = {
            "cls": cls,
            "args": args
        }
