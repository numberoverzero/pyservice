"""
These classes are responsible for managing state during a client/service
request, particularly to minimize the burden on plugins to manage context
"""
from . import common
from . import wsgi
import requests


def service(service, operation, request_body):
    process = ServiceProcessor(service, operation, request_body)
    return process()


def client(client, operation, request_body):
    process = ClientProcessor(client, operation, request_body)
    return process()


class ServiceProcessor(object):
    def __init__(self, service, operation, request_body):
        """
        A python class with __init__ and 1 or 2 functions is usually an
        anti-pattern, but in this case we're using it to simplify the
        chaining contract for plugin authors.  This allows them to
        use context.process_request() without managing the state to pass
        to the next plugin, or in any way knowing if there is another plugin
        """
        self.service = service
        # Don't rely on context's operation to be immutable
        self.operation = operation

        self.context = common.Context(self)
        self.context.operation = operation
        self.context.service = service

        self.request = common.Container()
        self.request_body = request_body
        self.response = common.Container()
        self.response_body = None

        self.state = "request"  # request -> operation -> function
        self.index = -1

    def __call__(self):
        """ Entry point for external callers """
        if self.state is None:
            raise ValueError("Already processed request")
        try:
            self.continue_execution()
        except Exception as exception:
            self.raise_exception(exception)
        finally:
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


class ClientProcessor(object):
    def __init__(self, client, operation, request):
        self.client = client
        # Don't rely on context's operation to be immutable
        self.operation = operation

        self.context = common.Context(self)
        self.context.operation = operation
        self.context.client = client

        self.request = common.Container()
        self.request.update(request)
        self.request_body = None
        self.response = common.Container()
        self.response_body = None

        self.index = -1

    def __call__(self):
        """ Entry point for external callers """
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

        pattern = self.client.api["endpoint"]["client_pattern"]
        uri = pattern.format(operation=self.operation)
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
