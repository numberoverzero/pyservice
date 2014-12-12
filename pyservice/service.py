import logging
import wsgi
from .context import Processor
from .common import cache, ExceptionFactory
logger = logging.getLogger(__name__)


class Service(object):
    def __init__(self, **config):
        self.config = {}
        self.config.update(config)

        self.plugins = {
            "request": [],
            "operation": []
        }
        self.exceptions = ExceptionFactory()

    @cache
    def debugging(self):
        return self.config.get("debug", False)

    def plugin(self, *, scope, func=None):
        if scope not in ["request", "operation"]:
            raise ValueError("Unknown scope {}".format(scope))
        # Return decorator that takes function
        if not func:
            return lambda func: self.plugin(scope=scope, func=func)
        self.plugins[scope].append(func)
        return func

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
        run_config = self.config.copy()
        run_config.update(config)

        logger.info("Service uri is {}".format(self.endpoint["path"]))
        wsgi_app = wsgi.WSGIApplication(self, self.endpoint["path"])
        wsgi_server.run(wsgi_app, **run_config)

    def operation(self, name, *, func=None):
        if name not in self.operations:
            raise ValueError("Unknown operation {}".format(name))
        # Return decorator that takes function
        if not func:
            return lambda func: self.operation(name, func=func)
        self.operations[name].func = func
        return func

    def validate_params(self, version, operation):
        if version != self.version:
            msg = "Unsupported version {}".format(version)
            wsgi.abort(400, msg)
        if operation not in self.operations:
            msg = "Unsupported operation {}".format(operation)
            wsgi.abort(404, msg)

    def execute(self, *, version, operation, request_body):
        '''WSGI Application entry point'''
        self.validate_params(version, operation)
        operation = self.operations[operation]
        processor = Processor(self, operation, request_body)

        try:
            response_body = processor.execute()
            return response_body
        except Exception as exception:
            msg = "Exception during operation {}".format(operation)
            logger.exception(msg, exc_info=exception)
            wsgi.abort(wsgi.INTERNAL_ERROR)

    def invoke(self, operation, req, resp, ctx):
        try:
            operation.func(req, resp, ctx)
        except Exception as exception:
            self.raise_exception(operation, exception, req, resp, ctx)
        finally:
            ctx.process_request()

    def raise_exception(self, operation, exception, req, resp, ctx):
        cls = exception.__class__.__name__
        args = exception.args

        whitelisted = cls in operation.exceptions
        if not (whitelisted or self.debugging):
            cls = "ServiceException"
            args = ["Internal Error"]

        resp.__exception = {
            "cls": cls,
            "args": args
        }
