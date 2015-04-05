import functools
import requests

from . import common
from . import wsgi


class Client(object):
    def __init__(self, **api):
        common.update_missing(common.DEFAULT_API, api)
        compute_uri(api)
        self.api = api

        self.plugins = []
        self.exceptions = common.ExceptionFactory()

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


class ClientProcessor(object):
    def __init__(self, client, operation, request):
        self.client = client
        self.operation = operation

        self.context = common.Context(operation, self)
        self.context.client = client
        self.request = common.Container()
        self.request.update(request)
        self.request_body = None
        self.response = common.Container()
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
        self.request_body = common.serialize(self.request)

        uri = self.client.api["uri"].format(operation=self.operation)
        data = self.request_body
        timeout = self.client.api["timeout"]
        response = requests.post(uri, data=data, timeout=timeout)

        self.handle_http_errors(response)
        self.response_body = response.text
        common.deserialize(self.response_body, self.response)
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


def compute_uri(api):
    uri = "{scheme}://{host}:{port}{path}".format(**api["endpoint"])
    api["uri"] = uri.format(operation="{operation}", **api)
