import types
import sys
from .docstrings import docstring
from .chain import Chain


class Extensions(object):
    __noop = lambda *a, **kw: None

    def __init__(self, on_finalize=None):
        self.extensions = []
        self.finalized = False
        self.on_finalize = on_finalize or self.__noop

    def finalize(self):
        if self.finalized:
            return
        self.on_finalize()
        self.finalized = True
        self.chain = Chain(self.extensions)

    def append(self, extension):
        if self.finalized:
            raise ValueError("Cannot add an extension, already finalized")
        else:
            self.extensions.append(extension)

    def __call__(self, event, *args, **kwargs):
        if not self.finalized:
            self.finalize()
        return self.chain(event, *args, **kwargs)


@docstring
def Extension(func):
    doc = "Generated extension from function '{}':\n\n{}".format(
        func.__name__, func.__doc__)
    extension = _create_extension(func)
    extension.__doc__ = doc
    return extension


def _create_extension(func):
    def wrapper(self, next_handler, event, *args, **kwargs):
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
