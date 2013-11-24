import six
import sys
import requests
from pyservice import serialize
from pyservice.exception_factory import ExceptionContainer

def requests_wire_handler(uri, data='', timeout=None):
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

    def _attr(self, key, default):
        '''Load value - presedence is config -> description meta -> default'''
        value = self._config.get(key, None)
        value = value or self._description.metadata.get(key, None)
        return value or default

    def _call(self, operation, *args):
        uri = self._uri.format(operation=operation)

        # list -> dict
        desc_input = self._description.operations[operation].input
        signature = [field.name for field in desc_input]
        context = serialize.to_dict(signature, args)

        # dict -> wire
        data = self._serializer.serialize(context)

        # wire -> wire
        try:
            response = self._wire_handler(uri, data=data, timeout=self._timeout)
        except Exception:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            exc_type = self.exceptions.ServiceException
            exc_value = exc_type(exc_value)
            six.reraise(exc_type, exc_value, tb=exc_traceback)

        # wire -> dict
        context = self._serializer.deserialize(response)

        self._handle_exception(context)

        # dict -> list
        try:
            desc_output = self._description.operations[operation].output
            signature = [field.name for field in desc_output]
            result = serialize.to_list(signature, context)
        except Exception:
            raise self.exceptions.ServiceException("Server returned invalid/incomplete response")

        # Unpack empty lists and single values
        if not signature:
            return None
        elif len(signature) == 1:
            return result[0]
        else:
            return result

    def _handle_exception(self, context):
        if "__exception" in context and len(context) == 1:
            exception = context["__exception"]
            ex_cls = getattr(self.exceptions, exception["cls"])
            raise ex_cls(*exception["args"])
