import bottle
from pyservice import serialize


class Service(object):
    def __init__(self, description, **config):
        self.description = description
        self._func = {}
        self._run_config = {}
        self._init_config = config
        self._serializer = serialize.JsonSerializer()

        self._bottle = bottle
        self._app = bottle.Bottle()
        route = "/{service}/<operation>".format(service=self.description.name)
        self._app.post(route)(self._bottle_call)

    def _attr(self, key, default):
        '''Load value - presedence is run config -> init config -> description meta -> default'''
        value = self._run_config.get(key, None)
        value = value or self._init_config.get(key, None)
        value = value or self.description.metadata.get(key, None)
        return value or default

    def _bottle_call(self, operation):
        if operation not in self.description.operations:
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
        context = self._serializer.deserialize(body)

        try:
            # dict -> list
            desc_input = self.description.operations[operation].input
            signature = [field.name for field in desc_input]
            args = serialize.to_list(signature, context)

            # list -> list (input -> output)
            result = self._func[operation](*args)

            # list -> dict
            desc_output = self.description.operations[operation].output
            signature = [field.name for field in desc_output]
            context = serialize.to_dict(signature, result)

        except Exception as exception:
            context = self._handle_exception(exception)

        # dict -> wire
        return self._serializer.serialize(context)

    def _handle_exception(self, exception):
        cls = exception.__class__.__name__
        args = exception.args

        allowed_exceptions = [ex.name for ex in self.description.exceptions]
        whitelisted = cls in allowed_exceptions
        debugging = self._attr("debug", False)
        if not whitelisted and not debugging:
            cls = "ServiceException"
            args = ["Internal Error"]

        return {
            "cls": cls,
            "args": args
        }

    def operation(self, name=None, func=None, **kwargs):
        # @service
        # def name(arg):
        if callable(name):
            func, name = name, name.__name__
            name = func.__name__

        wrap = lambda func: self._wrap_func(name, func, **kwargs)

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
        desc_input = self.description.operations[operation].input
        signature = [field.name for field in desc_input]
        if list(varnames) != signature:
            msg = "Func signature '{}' does not match operation description '{}'"
            raise ValueError(msg.format(varnames, signature))

        self._func[operation] = func
        return func

    def run(self, *args, **config):
        self._run_config = config
        self._app.run(*args, **config)
