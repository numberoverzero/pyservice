import types
import six
import sys

def handler(func):
    '''
    Decorator for creating handlers out of generator functions
    Similar in usage to the @contextmanager decorator


    Typical usage:

        @handler
        def logger(context):
            # Before the rest of the handlers execute
            start_time = time.now()

            #Process the request
            yield

            # Log the request timing
            end_time = time.now()

            msg = "Operation {} completed in {} seconds."
            name = context["operation"].name
            logger.info(msg.format(name, end_time - start_time))

    The rest of the handlers in a chain are executed when control is yielded
    '''
    def wrapper(context, next_handler):
        # Before next handler
        gen = func(context)

        # If it's not a generator, don't execute the rest of the chain.
        # For whatever reason, the handler terminated the request
        if not isinstance(gen, types.GeneratorType):
            return

        try:
            # `yield` is just permission to continue the chain, don't need value
            six.advance_iterator(gen)
        except StopIteration:
            # If generator didn't yield (or isn't a generator)
            # then we're not calling the next in the chain
            return

        try:
            next_handler(context)
        except:
            # Two notes:
            #
            # Why catch here if we're going to throw through the generator?
            #   Because the generator isn't really a generator - it's a
            #   convenience for writing before/after blocks for request handling.
            #   Therefore, we want to let any except/finally/else blocks in the
            #   handler run against whatever was raised in the chain.
            #
            # Why catch everything?
            #   Unlikely though it is, the handler may want to do something
            #   with BaseException.  It's a little weird that we're injecting
            #   the exception back into the generator, but we don't want to
            #   yield away from the handler, hit an exception down the chain,
            #   and bail from this helper, not letting the handler we're
            #   wrapping process cleanup from the exception.
            instance = sys.exc_info()[1]
            gen.throw(instance)

        try:
            six.advance_iterator(gen)
        except StopIteration:
            # Expected - nothing to yield
            return
        else:
            # Found another yield, which doesn't make sense
            raise RuntimeError("handler didn't stop")
    return wrapper


def execute(context, handlers):
    # Storing index on the func
    # Python 2.x doesn't support nonlocal
    # Using the variable name `self` to indicate we're
    # doing some self-referential shit here

    def next_handler(context):
        self.index += 1
        if self.index >= len(handlers):
            return
        handlers[self.index](context, self)
    self = next_handler
    self.index = -1
    next_handler(context)
