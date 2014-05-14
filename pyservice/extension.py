import types
import six
import sys
import functools
import logging
from pyservice.docstrings import docstring
logger = logging.getLogger(__name__)


class Extension(object):
    '''
    Service or Client extension - can add behavior before an operation starts,
    a handler during operation execution, and behavior after an operation returns
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

    def before_operation(self, operation, context, next):
        next(operation, context)

    def handle_operation(self, operation, context, next):
        next(operation, context)

    def after_operation(self, operation, context, next):
        next(operation, context)

@docstring
def extension(func, hook="handle_operation"):
    # func isn't a func, it's a hook name
    if not callable(func):
        return functools.partial(extension, hook=func)

    if hook not in Extension.hooks:
        raise ValueError("Unknown hook '{}'".format(hook))
    attrs = {
        "__doc__": "Generated Extension '{}' for the '{}' hook".format(
            func.__name__, hook),
        hook: _wrap_hook(hook, func)
    }
    return type(func.__name__, (Extension,), attrs)

def _wrap_hook(hook, func):
    @functools.wraps
    def wrapper(self, operation, context, next):
        # Execute anything before the yield
        gen = func(operation, context)

        # If it's not a generator, don't execute the rest of the chain.
        # For whatever reason, the handler terminated the operation
        if not isinstance(gen, types.GeneratorType):
            return

        try:
            yielded_value = six.advance_iterator(gen)
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
            next(operation, context)
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
            six.advance_iterator(gen)
        except StopIteration:
            # Expected - nothing to yield
            return
        else:
            # Found another yield, which doesn't make sense
            raise RuntimeError("extension didn't stop")
    return wrapper

def execute(extensions, operation, context, hook):
    n = len(extensions)
    def next(operation, context):
        next.i += 1
        # Ran out of extensions
        if next.i >= n:
            return
        # Get the hook on the next extension
        bound_hook = getattr(extensions[next.i], hook)
        # Invoke the extension's hook with a callback to next
        bound_hook(operation, context, next)

    next.i = -1  # next will increment to 0 for first operation
    next(operation, context)
