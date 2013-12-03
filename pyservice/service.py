import bottle
from pyservice import serialize
from pyservice.handler import Stack


class Service(object):
    def __init__(self, description, **config):
        self._description = description
        self._func = {}
        self._run_config = {}
        self._init_config = config
        self._serializer = serialize.JsonSerializer()

        self._bottle = bottle
        self._app = bottle.Bottle()
        route = "/{service}/<operation>".format(service=self._description.name)
        self._app.post(route)(self._bottle_call)
        self._handlers = []

    def _attr(self, key, default):
        '''Load value - presedence is run config -> init config -> description meta -> default'''
        if key in self._run_config:
            return self._run_config[key]
        if key in self._init_config:
            return self._init_config[key]
        if key in self._description.metadata:
            return self._description.metadata[key]
        return default

    def _add_handler(self, handler):
        self._handlers.append(handler)

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

        # wire -> dict
        dict_input = self._serializer.deserialize(body)

        context = {
            "input": dict_input,
            "output": {},
            "operation": operation,
            "service": self
        }
        handlers = self._handlers[:] + [self._handle]
        Stack(handlers).execute(context)

        # dict -> wire
        return self._serializer.serialize(context["output"])

    def _handle(self, context, next_handler):
        try:
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

        except Exception as exception:
            context["output"] = self._handle_exception(exception)

        next_handler(context)

    def _handle_exception(self, exception):
        cls = exception.__class__.__name__
        args = exception.args

        whitelisted = cls in self._description.exceptions
        debugging = self._attr("debug", False)
        if not whitelisted and not debugging:
            cls = "ServiceException"
            args = ["Internal Error"]

        return { "__exception": {
            "cls": cls,
            "args": args
        }}

    def operation(self, name=None, func=None, **kwargs):
        # @service.operation
        # def name(arg):
        if callable(name):
            func, name = name, name.__name__
            name = func.__name__

        if name not in self._description.operations:
            raise ValueError("Unknown Operation '{}'".format(name))

        def wrap(func):
            return self._wrap_func(name, func, **kwargs)

        # service.operation("name", operation)
        if callable(func):
            return wrap(func)

        # @service.operation("name")
        else:
            # we need to return a decorator, since we don't have the function to decorate yet
            return wrap

    def _wrap_func(self, operation, func, **kwargs):
        # Function signature cannot include *args or **kwargs
        varnames = func.__code__.co_varnames
        argcount = func.__code__.co_argcount
        if len(varnames) != argcount:
            msg = "Invalid func sig: can only contain positional args (not *args or **kwargs)"
            raise ValueError(msg)

        # Args must be an exact ordered match
        desc_input = self._description.operations[operation].input
        signature = [field.name for field in desc_input]
        if list(varnames) != signature:
            msg = "Func signature '{}' does not match operation description '{}'"
            raise ValueError(msg.format(varnames, signature))

        self._func[operation] = func
        return func

    def run(self, *args, **config):
        self._run_config = config
        self._app.run(*args, **config)
