import functools
from . import common
from . import processors


class Client(object):
    # Processor class to use when handling WSGI operations.
    # Invoked as:
    #   response = __process__(client, operation, request)
    __process__ = processors.client

    def __init__(self, **api):
        self.api = api
        common.load_defaults(api)
        # Inserts format string at api["endpoint"]["client_pattern"]
        common.construct_client_pattern(api["endpoint"])

        self.plugins = {
            "request": [],
            "operation": []
        }
        self.exceptions = common.ExceptionFactory()

    def __getattr__(self, operation):
        if operation not in self.api["operations"]:
            raise ValueError("Unknown operation '{}'".format(operation))
        func = functools.partial(self, operation=operation)

        # Avoid __getattr__ overhead on next call
        setattr(self, operation, func)
        return func

    def plugin(self, scope, *, func=None):
        if scope not in ["request", "operation"]:
            raise ValueError("Unknown scope {}".format(scope))
        # Return decorator that takes function
        if not func:
            return lambda func: self.plugin(scope=scope, func=func)
        self.plugins[scope].append(func)
        return func

    def __call__(self, operation, **request):
        '''Entry point for remote calls'''
        return self.__process__(operation, request)
