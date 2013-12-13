import six
import sys
import logging
import requests
from pyservice import serialize, extension
from pyservice.exception_factory import ExceptionContainer
logger = logging.getLogger(__name__)

def requests_wire_handler(uri, data='', timeout=None):  # pragma: no cover
    '''Adapter for requests library'''
    response = requests.post(uri, data=data, timeout=timeout)
    response.raise_for_status()
    return response.text


class Client(object):
    '''
    # Local endpoint for a service

    # =================
    # Operations
    # =================
    # Operations are defined in the client's ServiceDescription,
    # and can be invoked as methods on the client.

    description = ServiceDescription({
        "name": "some_service",
        "operations": [
            {
                "name": "echo",
                "input": ["value1, value2"],
                "output": ["result1, result2"]
            }
        ]
    })
    echoer = Client(description)
    first, second = echoer.echo("Hello", "World")
    assert first == "Hello"
    assert second == "World"

    # =================
    # Exceptions
    # =================
    # Client functions throw real exceptions,
    # which are namespaced under client.exceptions.

    description = ServiceDescription({
        "name": "tasker",
        "operations": [
            {
                "name": "get_task",
                "input": ["task_id"],
                "output": ["name, description"]
            },
            {
                "name": "add_task",
                "input": ["name", "description"],
                "outout": ["task_id"]
            }
        ],
        "exceptions": [
            "KeyError",
            "InvalidTaskName"
        ]
    })
    todo = client(description)

    # Built-in exceptions can be caught directly,
    # and are also available under client.exceptions
    try:
        todo.get_task("InvalidKey")
    except KeyError:
        print("Unknown task_id")
    # same behavior:
    # except todo.ex.KeyError:
    #    print("Unknown task_id")


    # Custom exceptions from the server are caught
    # under client.exceptions, or client.ex for short
    try:
        todo.add_task("$_ invalid name", "this is a description")
    except todo.ex.InvalidTaskName:
        print("InvalidTaskName :(")

    # =================
    # Metadata
    # =================
    # client config is loaded from two places during __init__:
    # **config, which takes precedence
    # description.metadata
    # If neither is provided, the default passed to _attr
    # is returned

    description = ServiceDescription({
        "name": "some_service",
        "operations": ["void"],
        "metadata_attr": ["a", "list"],
        "both_attr": True
    })

    config = {
        "both_attr": False,
        "config_attr": ["some", "values"]
    }
    client = Client(description, **config)

    assert ["a", "list"] == client._attr("metadata_attr", "default")
    assert False == client._attr("both_attr", "default")
    assert ["some", "values"] == client._attr("config_attr", "default")
    assert "default" == client._attr("neither_attr", "default")
    assert None is client._attr("no default")

    # =================
    # Extensions
    # =================
    # See the readme section on client/service extensions.
    '''
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
        self.ex = self.exceptions = ExceptionContainer()
        self._extensions = []

    def _register_extension(self, extension):
        self._extensions.append(extension)
        logger.debug("Registered extension '{}'".format(extension))

    def _attr(self, key, default=None):
        '''Load value - presedence is config -> description meta -> default'''
        if key in self._config:
            return self._config[key]
        if key in self._description.metadata:
            return self._description.metadata[key]
        return default

    def _call(self, operation, *args):
        try:
            self.execute("before_operation", operation)

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
            self.execute("handle_operation", context)

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
        finally:
            self.execute("after_operation", operation)

    def execute(self, method, *args):
        extensions = self._extensions[:] + [self]
        extension.execute(extensions, method, *args)

    def before_operation(self, operation, next_handler):
        next_handler(operation)

    def after_operation(self, operation, next_handler):
        next_handler(operation)

    def handle_operation(self, context, next_handler):
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
