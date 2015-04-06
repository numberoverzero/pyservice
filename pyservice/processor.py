"""
These classes are responsible for managing state during a client/service
request, particularly to minimize the burden on plugins to manage context
"""
from . import common
from . import wsgi


class ServiceProcessor(object):
    def __init__(self, service, operation, request_body):
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
