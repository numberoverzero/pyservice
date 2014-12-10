import logging
import ujson
import wsgi
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
        run_config = self.config.copy()
        run_config.update(config)

        logger.info("Service uri is {}".format(self.endpoint["path"]))
        wsgi_app = wsgi.WSGIApplication(self, self.endpoint["path"])
        wsgi_server.run(wsgi_app, **run_config)

    def operation(self, *, name, func=None):
        if name not in self.operations:
            raise ValueError("Unknown operation: " + name)

        # Return decorator that takes function
        if func is None:
            return lambda func: self.operation(name=name, func=func)

        self.operations[name].func = func
        return func

    def validate_params(self, version, operation):
        if version != self.version:
            msg = "Unsupported version {}".format(version)
            wsgi.abort(400, msg)
        if operation not in self.operations:
            msg = "Unsupported operation {}".format(operation)
            wsgi.abort(404, msg)

    def __call__(self, *, version, operation, wire_in):
        '''WSGI Application entry point'''
        self.validate_params(version, operation)
        operation = self.operations[operation]
        context = {
            "operation": operation,
            "exception": {},
            "service": self
        }

        try:
            self.extensions("before_operation", operation, context)

            # Read request
            request = ujson.loads(wire_in)

            # before/after don't have acces to request/response
            context["request"] = request.get("request", {})
            context["response"] = {}

            self.extensions("operation", operation, context)

            # Serialize before the after handlers.  This allows extension-
            # dependent values, such as objects from a sqlalchemy session to be
            # serialized before the session is closed.
            wire_out = ujson.dumps({
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
