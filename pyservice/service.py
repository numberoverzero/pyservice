import builtins
import logging
import ujson
import wsgi
import collections
import common
logger = logging.getLogger(__name__)


class Service(object):
    def __init__(self, **config):
        self.config = {}
        self.config.update(config)

        # TODO: Add operation filtering
        self.plugins = {
            "request": [],
            "operation": []
        }
        self.exceptions = common.ExceptionFactory()

    @common.cache
    def debugging(self):
        return self.config.get("debug", False)

    def plugin(self, scope, *, func=None):
        if scope not in ["request", "operation"]:
            raise ValueError("Unknown scope {}".format(scope))
        # Return decorator that takes function
        if not func:
            return lambda func: self.plugin(scope=scope, func=func)
        self.plugins[scope].append(func)
        return func

    def operation(self, name, *, func=None):
        if name not in self.operations:
            raise ValueError("Unknown operation {}".format(name))
        # Return decorator that takes function
        if not func:
            return lambda func: self.operation(name=name, func=func)
        self.operations[name].func = func
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

    def execute(self, *, version, operation, request_body):
        '''WSGI Application entry point'''
        self.validate_params(version, operation)
        operation = self.operations[operation]
        processor = Processor(self, operation, request_body)
        return processor.execute()

    def validate_params(self, version, operation):
        if version != self.version:
            msg = "Unsupported version {}".format(version)
            wsgi.abort(404, msg)
        if operation not in self.operations:
            msg = "Unsupported operation {}".format(operation)
            wsgi.abort(404, msg)


class WSGIApplication(object):

    def __init__(self, service, pattern):
        self.service = service
        self.pattern = wsgi.build_pattern(pattern)

    def get_route_kwargs(self, path):
        r = self.pattern.search(path)
        if not r:
            wsgi.abort(wsgi.UNKNOWN_OPERATION)
        return r.groupdict()

    def __call__(self, environ, start_response):
        """WSGI entry point."""
        try:
            response = wsgi.Response()
            kwargs = self.get_route_kwargs(wsgi.path(environ))
            kwargs["request_body"] = wsgi.body(environ)
            response.body = self.service.execute(**kwargs)
        except wsgi.RequestException as exception:
            logger.debug(
                "RequestException during WSGIApplication call",
                exc_info=exception)
            response.exception(exception)
        except Exception as exception:
            logger.debug(
                "Unhandled exception during WSGIApplication call",
                exc_info=exception)
            response.exception(wsgi.INTERNAL_ERROR)

        start_response(response.status_line, response.headers_list)
        return response.body_raw


class Processor(object):
    def __init__(self, service, operation, request_body):
        self.service = service
        self.operation = operation

        self.context = Context(service, operation, self)
        self.request = Container()
        self.request_body = request_body
        self.response = Container()
        self.response_body = None

        self.state = "request"  # request -> operation -> function
        self.index = -1

    def execute(self):
        if self.state is None:
            raise ValueError("Already processed request")
        try:
            self.continue_execution()
            return self.response_body
        except Exception as exception:
            msg = "Exception during operation {}".format(self.operation.name)
            logger.exception(msg, exc_info=exception)
            self.raise_exception(exception)
            return self.response_body

    def raise_exception(self, exception):
        cls = exception.__class__.__name__
        args = exception.args

        # Don't let non-whitelisted exceptions escape if we're not debugging
        whitelisted = cls in self.operation.exceptions
        if not whitelisted and not self.service.debugging:
            wsgi.abort(wsgi.INTERNAL_ERROR)

        # Don't leak incomplete operation state
        self.response.clear()
        self.response["__exception__"] = {
            "cls": cls,
            "args": args
        }
        self._serialize_response()

    def continue_execution(self):
        self.index += 1
        plugins = self.service.plugins[self.state]
        n = len(plugins)

        if self.index > n:
            # Terminal point so that service.invoke
            # can safely call context.process_request()
            return
        elif self.index == n:
            # Last plugin of this type, either roll over to the next plugin
            # type, or invoke the function underneath it all
            if self.state == "request":
                self.index = -1
                self.state = "operation"

                self._deserialize_request()
                self.continue_execution()
                self._serialize_response()
            elif self.state == "operation":
                self.operation.func(self.operation, self.request,
                                    self.response, self.context)
                self.state = None
        # index < n
        else:
            if self.state == "request":
                plugins[self.index](self.context)
            elif self.state == "operation":
                plugins[self.index](self.request, self.response, self.context)

    def _deserialize_request(self):
        self.request.update(ujson.loads(self.request_body))

    def _serialize_response(self):
        self.response_body = ujson.dumps(self.response)


class Context(object):
    def __init__(self, service, operation, processor):
        self.service = service
        self.operation = operation
        self.processor = processor

    def process_request(self):
        self.processor.continue_execution()


class Container(collections.defaultdict):
    DEFAULT_FACTORY = lambda: None

    def __init__(self):
        super().__init__(self, Container.DEFAULT_FACTORY)

    def __getattr__(self, name):
        return self[name]

    def __setattr__(self, name, value):
        self[name] = value


class ExceptionFactory(object):
    '''
    Class for building and storing Exception types.
    Built-in exception names are reserved.
    '''
    def __init__(self):
        self.classes = {}

    def build_exception_class(self, name):
        self.classes[name] = type(name, (Exception,), {})
        return self.classes[name]

    def get_class(self, name):
        # Check builtins for real exception class
        cls = getattr(builtins, name, None)
        # Cached?
        if not cls:
            cls = self.classes.get(name, None)
        # Cache
        if not cls:
            cls = self.build_exception_class(name)
        return cls

    def exception(self, name, *args):
        return self.get_class(name)(*args)

    def __getattr__(self, name):
        return self.get_class(name)
