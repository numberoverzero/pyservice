import six
import sys
import requests
from pyservice import serialize
from pyservice.exception_factory import ExceptionContainer
from pyservice.handler import execute

def requests_wire_handler(uri, data='', timeout=None):  # pragma: no cover
    '''Adapter for requests library'''
    response = requests.post(uri, data=data, timeout=timeout)
    response.raise_for_status()
    return response.text


class Client(object):
    def __init__(self, description, **config):
        self._description = description
        self._config = config

        for operation in self._description.operations:
            def make_call_op(operation):
                # We need this nested function to create
                # a scope for the operation variable,
                # otherwise it gets the last value of the var
                # in the for loop it's under.
                return lambda *args: self._call(operation, *args)
            func = make_call_op(operation)
            setattr(self, operation, func)

        uri = {
            "schema": self._attr("schema", "http"),
            "host": self._attr("host", "localhost"),
            "port": self._attr("port", 8080),
            "service": self._description.name
        }
        self._uri = "{schema}://{host}:{port}/{service}/{{operation}}".format(**uri)
        self._serializer = serialize.JsonSerializer()
        self._wire_handler = requests_wire_handler
        self._timeout = self._attr("timeout", 5)
        self.exceptions = ExceptionContainer()
        self._handlers = []

    def _add_handler(self, handler):
        self._handlers.append(handler)

    def _attr(self, key, default=None):
        '''Load value - presedence is config -> description meta -> default'''
        if key in self._config:
            return self._config[key]
        if key in self._description.metadata:
            return self._description.metadata[key]
        return default

    def _call(self, operation, *args):
        # list -> dict
        desc_input = self._description.operations[operation].input
        signature = [field.name for field in desc_input]
        dict_input = serialize.to_dict(signature, args)

        context = {
            "input": dict_input,
            "output": {},
            "operation": operation,
            "client": self
        }
        handlers = self._handlers[:] + [self._handler]
        execute(context, handlers)

        # dict -> list
        try:
            desc_output = self._description.operations[operation].output
            signature = [field.name for field in desc_output]
            result = serialize.to_list(signature, context["output"])
        except Exception:
            raise self.exceptions.ServiceException("Server returned invalid/incomplete response")

        # Unpack empty lists and single values
        if not signature:
            return None
        elif len(signature) == 1:
            return result[0]
        else:
            return result

    def _handler(self, context, next_handler):
        # dict -> wire
        data = self._serializer.serialize(context["input"])

        # wire -> wire
        try:
            uri = self._uri.format(operation=context["operation"])
            response = self._wire_handler(uri, data=data, timeout=self._timeout)
        except Exception:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            exc_type = self.exceptions.ServiceException
            exc_value = exc_type(exc_value)
            six.reraise(exc_type, exc_value, tb=exc_traceback)

        # wire -> dict
        context["output"] = self._serializer.deserialize(response)

        # Handle exceptions in the handler so surrounding handlers can try/catch
        self._handle_exception(context["output"])

        next_handler(context)

    def _handle_exception(self, output):
        if "__exception" in output and len(output) == 1:
            exception = output["__exception"]
            ex_cls = getattr(self.exceptions, exception["cls"])
            raise ex_cls(*exception["args"])
