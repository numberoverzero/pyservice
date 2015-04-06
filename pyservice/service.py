from . import common
from . import processor
from . import wsgi


class Service(object):
    __proc__ = processor.ServiceProcessor

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
        # No validation until we ask for operation or body
        request = wsgi.Request(self, environ)
        response = wsgi.Response(start_response)

        try:
            process = self.__proc__(self, request.operation, request.body)
            response.body = process()
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
