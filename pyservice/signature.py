"""
Modified from Lib/inspect.py to ignore extra keyword args,
and skip all positional processing.
"""
import inspect

# These imports are only used in _bind
from inspect import (
    itertools,
    OrderedDict,
    _VAR_KEYWORD,
    _VAR_POSITIONAL,
    _POSITIONAL_ONLY
)


def signature(obj):
    real_signature = inspect.signature(obj)
    return CustomSignature(real_signature)


class CustomSignature(inspect.Signature):
    """
    What is this voodoo sorcery?  See:
        https://docs.python.org/3/library/inspect.html#inspect.Signature.bind
        https://docs.python.org/3/library/inspect.html#inspect.BoundArguments
    This subclass has two key differences:
        `bind` doesn't process positional args at all
        `bind` drops extra kwargs instead of throwing
    """
    def __init__(self, signature):
        self._return_annotation = signature._return_annotation
        self._parameters = signature._parameters

    def _bind(self, kwargs, *, partial=False):
        '''
        Private method.  Don't use directly.
        Modified from `inspect.Signature.bind`.  Does not
        support `*args` and extra (unmapped) `**kwargs`
        entries are ignored.
        '''

        arguments = OrderedDict()

        parameters = iter(self.parameters.values())
        parameters_ex = ()

        if partial:
            # Support for binding arguments to 'functools.partial' objects.
            # See 'functools.partial' case in 'signature()' implementation
            # for details.
            for param_name, param in self.parameters.items():
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

        return self._bound_arguments_cls(self, arguments)

    def bind(self, **kwargs):
        '''
        Modified from `inspect.Signature.bind`.  Does not
        support `*args` and extra (unmapped) `**kwargs`
        entries are ignored.
        '''
        return self._bind(kwargs)
