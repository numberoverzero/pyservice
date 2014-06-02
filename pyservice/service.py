import bottle
import functools
import logging
from .common import DEFAULT_CONFIG, scrub_output
from .extension import Extensions
from .exception_factory import ExceptionContainer
from .serialize import serializers
from .docstrings import docstring
logger = logging.getLogger(__name__)


@docstring
class Service(object):
    def __init__(self, description, **config):
        self.config = dict(DEFAULT_CONFIG)
        self.config.update(config)

        self.exceptions = ExceptionContainer()
        self.description = description
        self.exceptions = ExceptionContainer()
        self.extensions = Extensions(  # Add __handle after all extensions
            lambda: self.extensions.append(self.__handle))
        self.functions = {}

        # Building a bottle routing format
        # https://mysite.com/api/{protocol}/{version}/{operation}
        self.uri = self.description.endpoint["path"].format(
            protocol="<protocol>",
            version="<version>",
            operation="<operation>"
        )
        logger.info("Service uri is {}".format(self.uri))

        self.app = bottle.Bottle()
        self.app.post(self.uri)(self)
        self.serializer = serializers[self.config["protocol"]]

    def run(self, *args, **config):
        # Snapshot the set of extensions when the service starts
        self.extensions.finalize()
        self.config.update(config)
        self.app.run(*args, **self.config)

    def operation(self, *, name, func=None):
        if func is None:
            return lambda func: self.operation(name=name, func=func)

        if name not in self.description.operations:
            raise ValueError("Unknown operation: " + name)

        self.functions[name] = func
        return func

    def __call__(self, protocol, version, operation):
        '''Entry point from bottle'''
        logger.info("call(protocol={p}, version={v}, operation={o})".format(
            o=operation, p=protocol, v=version))

        if protocol != self.config["protocol"]:
            msg = "Unsupported protocol {}".format(protocol)
            logger.info(msg)
            bottle.abort(400, msg)

        if version != self.description.version:
            msg = "Unsupported version {}".format(version)
            logger.info(msg)
            bottle.abort(400, msg)

        if operation not in self.description.operations:
            msg = "Unsupported operation {}".format(operation)
            logger.info(msg)
            bottle.abort(404, msg)

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
            self.extensions("before_operation", operation, context)

            # Read request
            wire_in = bottle.request.body.read().decode("utf-8")
            request = self.serializer.deserialize(wire_in)
            context["request"] = request.get("request", {})

            # Process
            self.extensions("operation", operation, context)

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
            try:
                scrub_output(
                    out, self.description.operations[operation].output,
                    strict=self.config.get("strict", True))
            except KeyError:
                # Don't throw if we fail to scrub output, probably means
                # there was an exception and expected values are missing
                pass

            # Write response
            wire_out = self.serializer.serialize(out)
            return wire_out
        except Exception as exception:
            msg = "Exception during operation {}".format(operation)
            logger.exception(msg, exc_info=exception)
            bottle.abort(500, "Internal Error")
        finally:
            self.extensions("after_operation", operation, context)

    def __handle(self, next_handler, event, operation, context):
        logger.debug("handle(event={event}, context={context})".format(
            event=event, context=context))
        if event == "operation":
            try:
                func = self.functions[operation]
                func(context["request"], context["response"])
                next_handler(event, operation, context)
            except Exception as exception:
                self.raise_exception(operation, exception, context)
        else:
            # Pass through
            next_handler(event, operation, context)

    def raise_exception(self, operation, exception, context):
        cls = exception.__class__.__name__
        args = exception.args

        whitelisted = cls in self.description.operations[operation].exceptions
        debugging = self.config.get("debug", False)
        logger.debug("raise_exception(whitelist={w}, debugging={d})".format(
            w=whitelisted, d=debugging))
        if not (whitelisted or debugging):
            cls = "ServiceException"
            args = ["Internal Error"]

        context["exception"] = {
            "cls": cls,
            "args": args
        }
