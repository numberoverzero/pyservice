import wsgi
import logging
from .serialize import serializers
from .common import (
    cache,
    DEFAULT_CONFIG,
    Extensions,
    ExceptionFactory,
    load_operations
)
logger = logging.getLogger(__name__)


class Service(object):
    def __init__(self, service, **config):
        self.config = dict(DEFAULT_CONFIG)
        self.config.update(config)

        self.exceptions = ExceptionFactory()
        self.extensions = Extensions()

        for key, value in service.items():
            setattr(self, key, value)
        self.operations = load_operations(service.get("operations", {}))

        self.serializer = serializers[self.config["protocol"]]

    @cache
    def debugging(self):
        return self.config.get("debug", False)

    def run(self, wsgi_server, *args, **config):
        '''
        wsgi_server must have a .run(app, **kwargs) method which takes
        a WSGI application as its argument, and optional configuration.

        See http://legacy.python.org/dev/peps/pep-0333/ for WSGI specification
        and https://github.com/bottlepy/bottle/blob/master/bottle.py#L2618 for
        examples of various adapters for many frameworks, including
        CherryPy, Waitress, Paste, Tornado, AppEngine, Twisted, GEvent,
        Gunicorn, and many more.  These can all be dropped in for wsgi_server.
        '''
        # Add __handle after all extensions
        self.extensions.append(self.handle)
        # Snapshot the set of extensions when the service starts
        self.extensions.finalize()
        self.config.update(config)

        logger.info("Service uri is {}".format(self.endpoint["path"]))
        wsgi_app = wsgi.WSGIApplication(self, self.endpoint["path"])
        wsgi_server.run(wsgi_app, **self.config)

    def operation(self, *, name, func=None):
        if func is None:
            return lambda func: self.operation(name=name, func=func)

        if name not in self.operations:
            raise ValueError("Unknown operation: " + name)

        self.operations[name].func = func
        return func

    def validate_params(self, protocol, version, operation):
        if protocol != self.config["protocol"]:
            msg = "Unsupported protocol {}".format(protocol)
            wsgi.abort(400, msg)
        if version != self.version:
            msg = "Unsupported version {}".format(version)
            wsgi.abort(400, msg)
        if operation not in self.operations:
            msg = "Unsupported operation {}".format(operation)
            wsgi.abort(404, msg)

    def __call__(self, *, protocol, version, operation, wire_in):
        '''WSGI Application entry point'''
        self.validate_params(protocol, version, operation)
        operation = self.operations[operation]
        context = {
            "operation": operation,
            "exception": {},
            "service": self
        }

        try:
            self.extensions("before_operation", operation, context)

            # Read request
            request = self.serializer.deserialize(
                wire_in)

            # before/after don't have acces to request/response
            context["request"] = request.get("request", {})
            context["response"] = {}

            self.extensions("operation", operation, context)

            # Serialize before the after handlers.  This allows extension-
            # dependent values, such as objects from a sqlalchemy session to be
            # serialized before the session is closed.
            wire_out = self.serializer.serialize({
                "response": context.get("response", {}),
                "exception": context.get("exception", {})
            })

            # before/after don't have acces to request/response
            del context["request"]
            del context["response"]

            return wire_out
        except Exception as exception:
            msg = "Exception during operation {}".format(operation)
            logger.exception(msg, exc_info=exception)
            wsgi.abort(wsgi.INTERNAL_ERROR)
        finally:
            self.extensions("after_operation", operation, context)

    def handle(self, next_handler, event, operation, context):
        if event == "operation":
            try:
                operation.func(context["request"], context["response"])
                next_handler(event, operation, context)
            except Exception as exception:
                self.raise_exception(operation, exception, context)
        else:
            # Pass through
            next_handler(event, operation, context)

    def raise_exception(self, operation, exception, context):
        cls = exception.__class__.__name__
        args = exception.args

        whitelisted = cls in operation.exceptions
        if not (whitelisted or self.debugging):
            cls = "ServiceException"
            args = ["Internal Error"]

        context["exception"] = {
            "cls": cls,
            "args": args
        }
