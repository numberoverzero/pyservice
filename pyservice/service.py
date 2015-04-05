from . import common
from . import wsgi


class Service(object):
    def __init__(self, **api):
        self.api = api
        common.load_defaults(api)
        # Inserts regex at api["endpoint"]["service_pattern"]
        common.construct_service_pattern(api["endpoint"])

        self.plugins = {
            "request": [],
            "operation": []
        }
        self.functions = {}
        self.exceptions = common.ExceptionFactory()

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
        request = wsgi.Request(self, environ)
        response = wsgi.Response(start_response)

        try:
            processor = ServiceProcessor(self, request.operation, request.body)
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


class ServiceProcessor(object):
    def __init__(self, service, operation, request_body):
        self.service = service
        self.operation = operation

        self.context = common.Context(operation, self)
        self.context.service = service
        self.request = common.Container()
        self.request_body = request_body
        self.response = common.Container()
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

                common.deserialize(self.request_body, self.request)
                self.continue_execution()
                self.response_body = common.serialize(self.response)
            elif self.state == "operation":
                func = self.service.functions[self.operation]
                func(self.request, self.response, self.context)
                self.state = None
        # index < n
        elif self.index < n:
            if self.state == "request":
                plugins[self.index](self.context)
            elif self.state == "operation":
                plugins[self.index](self.request, self.response, self.context)

    def raise_exception(self, exception):
        name = exception.__class__.__name__
        args = exception.args

        # Don't let non-whitelisted exceptions escape if we're not debugging
        whitelisted = name in self.service.api["exceptions"]
        debugging = self.service.api["debug"]
        if not whitelisted and not debugging:
            raise wsgi.INTERNAL_ERROR

        # Don't leak incomplete operation state
        self.response.clear()
        self.response["__exception__"] = {
            "cls": name,
            "args": args
        }
        self.response_body = common.serialize(self.response)
