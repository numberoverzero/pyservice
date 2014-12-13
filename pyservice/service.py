import builtins
import functools
import logging
import ujson
import requests
from . import wsgi
import collections

logger = logging.getLogger(__name__)
DEFAULT_API = {
    "version": "0",
    "timeout": 60,
    "debug": False,
    "endpoint": {
        "scheme": "https",
        "host": "localhost",
        "port": 8080,
        "path": "/api/{version}/{operation}"
    },
    "operations": [],
    "exceptions": []
}


def copy_missing(dst, src):
    """Copy any keys in `src` to `dst` that are missing in `dst`"""
    for key, value in src.items():
        dst[key] = dst.get(key, value)


def compute_uri(api, consumer):
    if consumer is Client:
        uri = "{scheme}://{host}:{port}{path}".format(**api["endpoint"])
    else:  # consumer is Service:
        uri = api["endpoint"]["path"]
    api["uri"] = uri.format(operation="{operation}", **api)


class Client(object):
    def __init__(self, **api):
        copy_missing(api, DEFAULT_API)
        compute_uri(api, Client)
        self.api = api

        self.plugins = []
        self.exceptions = ExceptionFactory()

    def __getattr__(self, operation):
        if operation not in self.api["operations"]:
            raise ValueError("Unknown operation '{}'".format(operation))
        return functools.partial(self, operation=operation)

    def plugin(self, func):
        self.plugins.append(func)
        return func

    def __call__(self, operation, **request):
        '''Entry point for remote calls'''
        return ClientProcessor(self, operation, request).execute()


class Service(object):
    def __init__(self, **api):
        copy_missing(api, DEFAULT_API)
        compute_uri(api, Service)
        self.api = api
        self.pattern = wsgi.build_pattern(self.api["uri"])

        # TODO: Add operation filtering
        self.plugins = {
            "request": [],
            "operation": []
        }
        self.functions = {}
        self.exceptions = ExceptionFactory()

    def plugin(self, scope, *, func=None):
        if scope not in ["request", "operation"]:
            raise ValueError("Unknown scope {}".format(scope))
        # Return decorator that takes function
        if not func:
            return lambda func: self.plugin(scope=scope, func=func)
        self.plugins[scope].append(func)
        return func

    def operation(self, name, *, func=None):
        if name not in self.api["operations"]:
            raise ValueError("Unknown operation {}".format(name))
        # Return decorator that takes function
        if not func:
            return lambda func: self.operation(name=name, func=func)
        self.functions[name] = func
        return func

    def wsgi_application(self, environ, start_response):
        response = wsgi.Response(start_response)
        try:
            # Load operation name from path, abort if
            # there's nothing there.
            operation = wsgi.load_operation(self.pattern, environ)
            if operation not in self.api["operations"]:
                wsgi.abort(wsgi.UNKNOWN_OPERATION)
            request_body = wsgi.load_body(environ)
            response.body = self(operation, request_body)
            processor = ServiceProcessor(self, operation, request_body)
            response.body = processor.execute()
        # service should be serializing interal exceptions
        except Exception as exception:
            # Defined failure case -
            # invalid body, unknown path/operation
            if isinstance(exception, wsgi.RequestException):
                response.exception(exception)
            # Unexpected failure type
            else:
                response.exception(wsgi.INTERNAL_ERROR)
        finally:
            return response.send()


class ClientProcessor(object):
    def __init__(self, client, operation, request):
        self.client = client
        self.operation = operation

        self.context = Context(operation, self)
        self.context.client = client
        self.request = Container()
        self.request.update(request)
        self.request_body = None
        self.response = Container()
        self.response_body = None

        self.index = -1

    def execute(self):
        self.continue_execution()
        return self.response

    def continue_execution(self):
        self.index += 1
        plugins = self.client.plugins
        n = len(plugins)

        if self.index == n:
            # Last plugin of this type, package args and invoke remote call
            self.remote_call()
        # index < n
        elif self.index < n:
            plugins[self.index](self.request, self.response, self.context)
        else:
            # BUG - index > n means processor ran index over plugin length
            raise ValueError("Bug in pyservice.ClientProcessor!")

    def remote_call(self):
        self.request_body = serialize(self.request)

        uri = self.client.api["uri"].format(operation=self.operation)
        data = self.request_body
        timeout = self.client.api["timeout"]
        response = requests.post(uri, data=data, timeout=timeout)

        self.handle_http_errors(response)
        deserialize(self.response_body, self.response)
        self.handle_service_exceptions()

    def handle_http_errors(self, response):
        if wsgi.is_request_exception(response):
            message = "{} {}".format(response.status_code, response.reason)
            self.raise_exception({
                "cls": "RequestException",
                "args": (message,)
            })

    def handle_service_exceptions(self):
        exception = self.response.get("__exception__", None)
        if exception:
            # Don't leak incomplete operation state
            self.response.clear()
            self.raise_exception(exception)

    def raise_exception(self, exception):
        name = exception["cls"]
        args = exception["args"]
        exception = getattr(self.client.exceptions, name)(*args)
        raise exception


class ServiceProcessor(object):
    def __init__(self, service, operation, request_body):
        self.service = service
        self.operation = operation

        self.context = Context(operation, self)
        self.context.service = service
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
            msg = "Exception during operation {}".format(self.operation)
            logger.exception(msg, exc_info=exception)
            self.raise_exception(exception)
            return self.response_body

    def continue_execution(self):
        self.index += 1
        plugins = self.service.plugins[self.state]
        n = len(plugins)

        if self.index == n:
            # Last plugin of this type, either roll over to the next plugin
            # type, or invoke the function underneath it all
            if self.state == "request":
                self.index = -1
                self.state = "operation"

                deserialize(self.request_body, self.request)
                self.continue_execution()
                self.response_body = serialize(self.response)
            elif self.state == "operation":
                func = self.service.functions[self.operation]
                func(self.operation, self.request, self.response, self.context)
                self.state = None
        # index < n
        elif self.index < n:
            if self.state == "request":
                plugins[self.index](self.context)
            elif self.state == "operation":
                plugins[self.index](self.request, self.response, self.context)
        else:
            # BUG - index > n means processor ran index over plugin length
            wsgi.abort(wsgi.INTERNAL_ERROR)

    def raise_exception(self, exception):
        name = exception.__class__.__name__
        args = exception.args

        # Don't let non-whitelisted exceptions escape if we're not debugging
        whitelisted = name in self.service.api["exceptions"]
        debugging = self.service.api["debug"]
        if not whitelisted and not debugging:
            wsgi.abort(wsgi.INTERNAL_ERROR)

        # Don't leak incomplete operation state
        self.response.clear()
        self.response["__exception__"] = {
            "cls": name,
            "args": args
        }
        self.response_body = serialize(self.response)


def serialize(container):
    return ujson.dumps(container)


def deserialize(string, container):
    container.update(ujson.loads(string))


class Context(object):
    def __init__(self, operation, processor):
        self.operation = operation
        self.__processor__ = processor

    def process_request(self):
        self.__processor__.continue_execution()


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
