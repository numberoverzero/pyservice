import logging
import inspect
import bottle
from pyservice.exception_factory import ExceptionContainer
from pyservice.serialize import serialize
from pyservice.extension import extension
logger = logging.getLogger(__name__)


class Service(object):
    '''
    # Remote endpoint for a service

    # =================
    # Operations
    # =================
    # Operations are defined in the service's Description,
    # and should be mapped to a function with the same input
    # using the Serivice.operation decorator

    description = ServiceDescription({
        "name": "some_service",
        "operations": {
            "echo": {
                "input": {
                    "value1": {},
                    "value2": {}
                },
                "output": {
                    "result1": {},
                    "result2": {}
                }
            }
        }
    })
    service = Service(description)

    @service.operation("echo")
    def echo_func(value1, value2):
        return value1, value2

    # =================
    # Exceptions
    # =================
    # Exceptions thrown are sent back to the client and raised
    # When not debugging, only whitelisted (included in
    # service description) exceptions are thrown -
    # all other exceptions are returned as a generic
    # ServiceException.
    # Like the Client, exceptions can be referenced
    # through the service itself.  Both of the following
    # are valid:
    #     raise service.exceptions.InvalidId
    #     raise service.ex.InvalidId

    description = ServiceDescription({
        "name": "tasker",
        "operations": [
            {
                "name": "get_task",
                "input": ["task_id"],
                "output": ["name", "description"]
            }
        ],
        "exceptions": [
            KeyError,
            InvalidId
        ]
    })
    service = Service(description)
    tasks = {}

    @service.operation("get_task")
    def operation(task_id):
        if not valid_format(task_id):
            raise InvalidId(task_id)
        return tasks[task_id]  # Can raise KeyError

    # =================
    # Extensions
    # =================
    # See the readme section on client/service extensions.
    '''
    def __init__(self, description, serializer, **config):
        self.config = {}
        self.config.update(description)
        self.config.update(config)

        self._description = description
        self._func = {}
        self.serializer = serializer

        self._bottle = bottle
        self._app = bottle.Bottle()
        route = "/{service}/<operation>".format(service=self._description.name)
        self._app.post(route)(self._bottle_call)
        self.ex = self.exceptions = ExceptionContainer()
        self._extensions = []

    def add_extension(self, extension):
        self._extensions.append(extension)
        logger.debug("Registered extension '{}'".format(extension))

    def _bottle_call(self, operation):
        if operation not in self._description.operations:
            self._bottle.abort(404, "Unknown Operation '{}'".format(operation))
        try:
            body = self._bottle.request.body.read().decode("utf-8")
            return self._call(operation, body)
        except Exception:
            self._bottle.abort(500, "Internal Error")

    def _call(self, operation, body):
        '''
        operation: operation name
        body: request body (string)
        '''
        try:
            self.execute("before_operation", operation)

            # wire -> dict
            dict_input = self.serializer.deserialize(body)

            context = {
                "input": dict_input,
                "output": {},
                "operation": operation,
                "service": self
            }
            try:
                self.execute("handle_operation", context)
            except Exception as exception:
                context["output"] = self._handle_exception(exception)

            # dict -> wire
            return self.serializer.serialize(context["output"])
        finally:
            self.execute("after_operation", operation)

    def execute(self, method, *args):
        extensions = self._extensions[:] + [self]
        extension.execute(extensions, method, *args)

    def handle_operation(self, context, next_handler):
        # dict -> list
        desc_input = self._description.operations[context["operation"]].input
        signature = [field.name for field in desc_input]
        args = serialize.to_list(signature, context["input"])

        # list -> list (input -> output)
        result = self._func[context["operation"]](*args)

        # list -> dict
        desc_output = self._description.operations[context["operation"]].output
        signature = [field.name for field in desc_output]

        # Assume that if signature has 1 (or 0, which is really 1) output field,
        # result is correct, even if result is iterable (such as lists)
        if len(signature) == 1:
            result = [result]
        context["output"] = serialize.to_dict(signature, result)
        next_handler(context)

    def _handle_exception(self, exception):
        cls = exception.__class__.__name__
        args = exception.args

        whitelisted = cls in self._description.exceptions
        debugging = self.config.get("debug", False)
        if not whitelisted and not debugging:
            cls = "ServiceException"
            args = ["Internal Error"]

        return { "__exception": {
            "cls": cls,
            "args": args
        }}

    def operation(self, name, **kwargs):
        if name not in self._description.operations:
            raise ValueError("Unknown Operation '{}'".format(name))

        def wrapper(func):
            # Function signature cannot include *args or **kwargs
            spec = inspect.getargspec(func)
            if spec.varargs or spec.keywords or spec.defaults:
                msg = "Invalid func sig: can only contain positional args (not *args or **kwargs)"
                raise ValueError(msg)

            # Args must be an exact ordered match
            desc_input = self._description.operations[name].input
            signature = [field.name for field in desc_input]
            if list(spec.args) != signature:
                msg = "Func signature '{}' does not match operation description '{}'"
                raise ValueError(msg.format(spec.args, signature))

            self._func[name] = func

            # Return the input function for testing, local calls, etc.
            return func
        return wrapper

    def run(self, *args, **config):
        self.validate()
        self.config.update(config)
        self._app.run(*args, **config)

    def validate(self):
        expected_operations = set(self._description.operations)
        actual_operations = set(self._func)

        if expected_operations != actual_operations:
            raise ValueError("Expected operations {} but found operations {} instead.".format(
                expected_operations, actual_operations))


class WebService(Service):
    def __init__(self, description, **config):
        serializer = serialize.JsonSerializer()
        super(WebService, self).__init__(description, serializer, **config)
