"""
Modified from Lib/inspect.py to ignore extra keyword args,
and skip all positional processing.
"""
import inspect

# These imports are only used in _bind
from inspect import (
    itertools,
    OrderedDict,
    BoundArguments,
    Parameter,
    signature,
    _empty,
    _VAR_KEYWORD,
    _VAR_POSITIONAL,
    _POSITIONAL_ONLY,
    _POSITIONAL_OR_KEYWORD,
    _KEYWORD_ONLY
)

validate_fail = "Invalid params for signature: "
bad_param_type = (validate_fail + "expected function arg {}'s type "
                  + "to be positional or keyword, found {} instead.")
missing_param = (validate_fail + "function missing expected params {}.")
unbound_param = (validate_fail + "function expected undeclared param {}.")


class Binding(object):
    def __init__(self, func, input, output):
        self.func = func
        self.sig = signature(func)
        self.input = input
        self.output = output
        self._validate_input()

    def __call__(self, kwargs, restrict=True):
        '''
        Bind kwargs to func and invoke.  If restrict, only bind
        values in self.input, and only return values in self.output
        '''
        if restrict:
            kwargs = {kwargs[k] for k in self.input}

        bound_args = self._bind(kwargs)
        result = self.func(*bound_args.args, **bound_args.kwargs)

        if restrict:
            result = {result[k] for k in self.output}

        return result

    def _validate_input(self):
        # All of these parameters need to be present
        minimum_params = set(self.input)

        # The parameter names of the function
        actual_params = set(self.sig.parameters)
        has_var_kwargs = False

        # Copy so we can mutate actual_params
        for pname in set(actual_params):
            param = self.sig.parameters[pname]
            if pname in minimum_params:
                if param.kind in (_VAR_KEYWORD, _VAR_POSITIONAL):
                    # Binding *args, **kwargs is not intuitive
                    raise TypeError(bad_param_type.format(pname, param.kind))
                else:
                    # This is a positional or keyword arg in both minimum and
                    # actual params, so we'll have a value.
                    actual_params.remove(pname)
                    minimum_params.remove(pname)
            else:
                # param is declared in func signature but not in minimum params
                # this is ok as long as the func signature uses this for
                # var_keyword or var_positional
                if param.kind == _VAR_POSITIONAL:
                    actual_params.remove(pname)
                elif param.kind == _VAR_KEYWORD:
                    # Since this is **kwargs, this method can catch extra
                    # variables
                    has_var_kwargs = True
                    actual_params.remove(pname)
                elif param.default is not Parameter.empty:
                    # This is a positional or keyword arg with a default,
                    # so it doesn't need to be present in minimum params
                    actual_params.remove(pname)
                else:
                    # Not a var* and doesn't have a default - minimum params
                    # doesn't include this varible and the function doesn't
                    # have a value for it.  Strict binding will always fail
                    raise TypeError(unbound_param.format(pname))
        # At this point actual_params should be empty - every code path either
        # removes or throws.
        if actual_params:
            raise TypeError("Failed to match signature, there is a bug in"
                            + "Binding._validate_params!")
        # It's ok for minimum_params to be non-empty, as long as the function
        # has a var_kwargs to catch extra values.  If the function doesn't,
        # params that are expected to bind will always be omitted
        if minimum_params and not has_var_kwargs:
            raise TypeError(missing_param.format(minimum_params))

        # Otherwise we've matched all params, or the function's
        # defaults/**kwargs will take care of things

    def _bind(self, kwargs, *, partial=False):
        '''
        Modified from `inspect.Signature.bind`.  Does not
        support `*args` and extra (unmapped) `**kwargs`
        entries are ignored.

        What is this voodoo sorcery?  See:
            https://docs.python.org/3/library/inspect.html
                    #inspect.Signature.bind
                    #inspect.BoundArguments
        This subclass has two key differences:
            `bind` doesn't process positional args at all
            `bind` drops extra kwargs instead of throwing
        '''

        arguments = OrderedDict()
        parameters = iter(self.sig.parameters.values())
        parameters_ex = ()

        if partial:
            # Support for binding arguments to 'functools.partial' objects.
            # See 'functools.partial' case in 'signature()' implementation
            # for details.
            for param_name, param in self.sig.parameters.items():
                if (param._partial_kwarg and param_name not in kwargs):
                    # Simulating 'functools.partial' behavior
                    kwargs[param_name] = param.default

        while True:
            try:
                param = next(parameters)
            except StopIteration:
                # No more parameters. That's it. Just need to check that
                # we have no `kwargs` after this while loop
                break
            else:
                if param.kind == _VAR_POSITIONAL:
                    # That's OK, just empty *args.  Let's start parsing
                    # kwargs
                    break
                elif param.name in kwargs:
                    if param.kind == _POSITIONAL_ONLY:
                        msg = '{arg!r} parameter is positional only, ' \
                              'but was passed as a keyword'
                        msg = msg.format(arg=param.name)
                        raise TypeError(msg) from None
                    parameters_ex = (param,)
                    break
                elif (param.kind == _VAR_KEYWORD or
                        param.default is not _empty):
                    # That's fine too - we have a default value for this
                    # parameter.  So, lets start parsing `kwargs`, starting
                    # with the current parameter
                    parameters_ex = (param,)
                    break
                else:
                    # No default, not VAR_KEYWORD, not VAR_POSITIONAL,
                    # not in `kwargs`
                    if partial:
                        parameters_ex = (param,)
                        break
                    else:
                        msg = '{arg!r} parameter lacking default value'
                        msg = msg.format(arg=param.name)
                        raise TypeError(msg) from None

        # Now, we iterate through the remaining parameters to process
        # keyword arguments
        kwargs_param = None
        for param in itertools.chain(parameters_ex, parameters):
            if param.kind == _VAR_KEYWORD:
                # Memorize that we have a '**kwargs'-like parameter
                kwargs_param = param
                continue

            if param.kind == _VAR_POSITIONAL:
                # Named arguments don't refer to '*args'-like parameters.
                # We only arrive here if the positional arguments ended
                # before reaching the last parameter before *args.
                continue

            param_name = param.name
            try:
                arg_val = kwargs.pop(param_name)
            except KeyError:
                # We have no value for this parameter.  It's fine though,
                # if it has a default value, or it is an '*args'-like
                # parameter, left alone by the processing of positional
                # arguments.
                if (not partial and param.kind != _VAR_POSITIONAL and
                        param.default is _empty):
                    raise TypeError('{arg!r} parameter lacking default value'
                                    .format(arg=param_name)) from None

            else:
                if param.kind == _POSITIONAL_ONLY:
                    # This should never happen in case of a properly built
                    # Signature object (but let's have this check here
                    # to ensure correct behaviour just in case)
                    raise TypeError('{arg!r} parameter is positional only, '
                                    'but was passed as a keyword'
                                    .format(arg=param.name))

                arguments[param_name] = arg_val

        if kwargs:
            if kwargs_param is not None:
                # Process our '**kwargs'-like parameter
                arguments[kwargs_param.name] = kwargs

        return BoundArguments(self.sig, arguments)
