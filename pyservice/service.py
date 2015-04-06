from . import common
from . import processors
from . import wsgi


class Service(object):
    # Processor class to use when handling WSGI operations.
    # Invoked as:
    #   response = __process__(service, operation, body)()
    __process__ = processors.service

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
        # environ isn't validated until we ask for operation or body
        req = wsgi.Request(self, environ)
        resp = wsgi.Response(start_response)

        try:
            resp.body = self.__process__(self, req.operation, req.body)
        except Exception as exception:
            # Defined failure case -
            # invalid body, unknown path/operation
            if isinstance(exception, wsgi.RequestException):
                resp.exception(exception)
            # Unexpected failure type - don't propagate to consumers
            else:
                resp.exception(wsgi.INTERNAL_ERROR)
        finally:
            return resp.send()
