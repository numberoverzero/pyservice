import types
import sys
import functools
import logging
from pyservice.docstrings import docstring
logger = logging.getLogger(__name__)


class Extension(object):
    '''
    Service or Client extension - can add behavior before an
    operation starts, a handler during operation execution,
    and behavior after an operation returns
    '''
    hooks = [
        "before_operation",
        "handle_operation",
        "after_operation"
    ]

    def __init__(self, obj, **kwargs):
        self.obj = obj
        obj._extentions.append(self)
        logger.debug(
            "Registered extension '{}' to object '{}'".format(
                extension, obj._description.name))

    def before_operation(self, next_handler, operation, context):
        next_handler(operation, context)

    def handle_operation(self, next_handler, operation, context):
        next_handler(operation, context)

    def after_operation(self, next_handler, operation, context):
        next_handler(operation, context)


@docstring
def extension(func, hook="handle_operation"):
    # func isn't a func, it's a hook name
    if not callable(func):
        return functools.partial(extension, hook=func)

    if hook not in Extension.hooks:
        raise ValueError("Unknown hook '{}'".format(hook))

    doc = "Generated Extension '{}' for the '{}' hook\n\n{}"
    attrs = {
        "__doc__": doc.format(func.__name__, hook, func.__doc__),
        hook: _wrap_hook(hook, func)
    }
    return type(func.__name__, (Extension,), attrs)


def _wrap_hook(hook, func):
    @functools.wraps
    def wrapper(self, next_handler, operation, context):
        # Execute anything before the yield
        gen = func(operation, context)

        # If it's not a generator, don't execute the rest of the chain.
        # For whatever reason, the handler terminated the operation
        if not isinstance(gen, types.GeneratorType):
            return

        try:
            yielded_value = next(gen)
            # if there's a return of two values, push those into the next
            # handler.  Otherwise, use original operation/context
            if yielded_value and len(yielded_value) == 2:
                # function yielded operation, context
                operation, context = yielded_value
        except StopIteration:
            # If generator didn't yield (or isn't a generator)
            # then we're not calling the next in the chain
            return

        try:
            next_handler(operation, context)
        except:
            # Why catch here if we're going to throw through the generator?
            #  The wrapped function isn't really a generator - it's a
            #  convenience for wrapping handle_operation. We want to let any
            #  except/finally/else blocks in the extension run against
            #  whatever was raised in the chain.
            #
            # Why catch everything?
            #  The extension may want to do something with BaseException.
            #  It's a little weird that we're injecting the exception back
            #  into the generator, but we don't want to yield away from the
            #  extension, hit an exception down the chain, and bail from
            #  this helper, not letting the extension we're wrapping process
            #  cleanup from the exception.
            instance = sys.exc_info()[1]
            gen.throw(instance)

        try:
            next(gen)
        except StopIteration:
            # Expected - nothing to yield
            return
        else:
            # Found another yield, which doesn't make sense
            raise RuntimeError("extension didn't stop")
    return wrapper


def noop(*args, **kwargs):
    pass


class Chain(object):
    def __init__(self, objs):
        self.__objs = objs
        self.__chain = {}

    def __getattr__(self, name):
        # Bind the partial so next call avoids the __getattr__ overhead
        func = functools.partial(self.__invoke, name)
        setattr(self, name, func)
        # Since we're only here once, compile the partial chain
        self.__compile(name)

        return func

    def __compile(self, name):
        next_obj = noop
        for obj in reversed(self.__objs):
            func = getattr(obj, name, None)
            if func:
                next_obj = functools.partial(func, next_obj)
        self.__chain[name] = next_obj

    def __invoke(self, name, *args, **kwargs):
        return self.__chain[name](*args, **kwargs)


def compiled_extension_chain(extensions):
    '''Pre-compile extension hooks'''
    chain = Chain(extensions)
    for hook in Extension.hooks:
        getattr(chain, hook)
    return chain
