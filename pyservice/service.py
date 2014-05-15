import bottle
import functools
import logging
from pyservice.exception_factory import ExceptionContainer
from pyservice.serialize import JsonSerializer
from pyservice.handlers import BottleHandler
from pyservice.extension import execute
from pyservice.docstrings import docstring
from pyservice.util import filtered_copy
from pyservice.binding import Binding
logger = logging.getLogger(__name__)


@docstring
class Service(object):
    def __init__(self, description, handler, **kwargs):
        self.functions = {}
        self.exceptions = ExceptionContainer()
        self.extensions = []

        self.description = description
        self.handler = handler
        self.kwargs = kwargs or {}

        service_name = self.description.name
        pattern = "/{service}/<operation>".format(service=service_name)
        self.handler.route(service_name, self, pattern)

    def run(self, *args, **kwargs):
        self.kwargs.update(kwargs)
        self.handler.run(*args, **self.kwargs)

    def operation(self, func, name=None):
        # func isn't a func, it's the operation name
        if not callable(func):
            return functools.partial(self.operation, name=func)

        if name not in self.description.operations:
            raise ValueError("Unknown Operation '{}'".format(name))

        self.bindings[name] = Binding(
            func,
            self.description.operations[name].input,
            self.description.operations[name].output)
        return func

    def call(self, operation, request):
        '''Entry point from handler'''
        extensions = self.extensions[:] + [self]
        context = {
            "__exception": {},
            "request": request,
            "response": {},

            # Meta about this operation
            "extensions": extensions,
            "operation": operation,
            "service": self
        }
        fire = functools.partial(execute, extensions, operation, context)

        try:
            fire("before_operation")
            fire("handle_operation")
        except Exception as exception:
            # Catch exception here instead of inside handle_operation
            # so that extensions can try/catch
            self.raise_exception(operation, exception, context)
        finally:
            # Don't wrap this fire in try/catch, handler will catch as an
            # internal failure
            fire("after_operation")
            # Always give context back to the handler, so it can pass along
            # request and __exception
            return context

    def handle_operation(self, operation, context, next_handler):
        result = self.bindings[operation](context["request"])

        # TODO: validate result against expected service output

        context["response"].update(result)
        next_handler(operation, context)

    def raise_exception(self, operation, exception, context):
        cls = exception.__class__.__name__
        args = exception.args

        whitelisted = cls in self.description.operations[operation].exceptions
        debugging = self.config.get("debug", False)
        if not (whitelisted or debugging):
            cls = "ServiceException"
            args = ["Internal Error"]

        context["__exception"] = {
            "cls": cls,
            "args": args
        }


class WebService(Service):
    def __init__(self, description, **kwargs):
        serializer = JsonSerializer()
        handler = BottleHandler(serializer)
        super(WebService, self).__init__(description, handler, **kwargs)
