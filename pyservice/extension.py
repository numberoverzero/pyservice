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
    events = [
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

    def handle(self, next_handler, event, *args, **kwargs):
        next_handler(event, *args, **kwargs)


@docstring
def extension(func, *, event="handle_operation"):
    if event not in Extension.events:
        raise ValueError("Unknown event '{}'".format(event))

    doc = "Generated Extension '{}' for the '{}' event:\n\n{}"
    attrs = {
        "__doc__": doc.format(func.__name__, event, func.__doc__),
        "handle": _wrap_hook(func, event)
    }
    return type(func.__name__, (Extension,), attrs)


def _wrap_hook(func, expected_event):
    @functools.wraps
    def wrapper(self, next_handler, event, *args, **kwargs):
        if event != expected_event:
            # This extension doesn't handle the event, just pass through
            next_handler(event, *args, **kwargs)
            return

        # Execute anything before the yield
        gen = func(event, *args, **kwargs)

        # If it's not a generator, don't execute the rest of the chain.
        # For whatever reason, the handler terminated the operation
        if not isinstance(gen, types.GeneratorType):
            return

        try:
            next(gen)
        except StopIteration:
            # If generator didn't yield (or isn't a generator)
            # then we're not calling the next in the chain
            return

        try:
            next_handler(*args, **kwargs)
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
