import bottle
import functools
import logging
from pyservice.exception_factory import ExceptionContainer
from .serialize import serializers
from pyservice.extension import execute
from pyservice.docstrings import docstring
logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "protocol": "json"
}


@docstring
class Service(object):
    def __init__(self, description, **config):
        self.config = dict(DEFAULT_CONFIG)
        self.config.update(config)

        self.functions = {}
        self.exceptions = ExceptionContainer()
        self.extensions = []

        self.description = description

        # Building a bottle routing format
        # https://mysite.com/api/{protocol}/{version}/{operation}
        self.uri = self.description["endpoint"].format(
            protocol="<protocol>",
            version="<version>",
            operation="<operation>"
        )

        self.app = bottle.Bottle()
        self.app.post(self.uri)(self.route)
        self.serializer = serializers[self.config["protocol"]]

    def run(self, *args, **config):
        run_config = dict(self.config)
        run_config.update(config)
        self.handler.run(*args, **run_config)

    def operation(self, func, name=None):
        # func isn't a func, it's the operation name
        if not callable(func):
            return functools.partial(self.operation, name=func)

        if name not in self.description.operations:
            raise ValueError("Unknown operation: " + name)

        self.functions[name] = func
        return func

    def route(self, protcol, version, operation):
        '''Entry point from bottle'''
        if protocol != self.config["protocol"]:
            bottle.abort(400, "Unsupported protocol: " + protocol)
        if version != self.description["version"]:
            bottle.abort(400, "Unsupported version: " + version)
        if operation not in self.description.operations:
            bottle.abort(404, "Unknown operation: " + operation)
        try:
            # Read request
            body = bottle.request.body.read().decode("utf-8")
            wire_in = self.serializer.deserialize(body)

            # Process
            request = wire_in["request"]
            response = self.call(operation, request)

            # Write response
            wire_out = self.serializer.serialize({
                "response": response.get("response", {}),
                "exception": response.get("exception", {})
            })
            return wire_out
        except Exception:
            bottle.abort(500, "Internal Error")

    def call(self, operation, request):
        '''Invoked from route'''
        extensions = self.extensions[:] + [self]
        context = {
            "exception": {},
            "request": request,
            "response": {},

            # Meta about this operation
            "extensions": extensions,
            "operation": operation,
            "description": self.description,
            "service": self
        }
        fire = functools.partial(execute, extensions, operation, context)

        try:
            fire("before_operation")
            fire("handle_operation")
        except Exception as exception:
            # Catch exception here instead of inside handle_operation
            # so that extensions can try/catch
            self.raise_exception(operation, exception, context)
        finally:
            # Don't wrap this fire in try/catch, handler will catch as an
            # internal failure
            fire("after_operation")
            # Always give context back to the handler, so it can pass along
            # request and exception
            return context

    def handle_operation(self, operation, context, next_handler):
        self.functions[operation](context["request"], context["response"])
        next_handler(operation, context)

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
