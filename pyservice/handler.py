import functools

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
    @functools.wraps(func)
    def wrapper(context, next_handler):
        # Before next handler
        gen = func(context)
        try:
            # `yield` is just permission to continue the chain, don't need value
            gen.next()
        except (AttributeError, StopIteration):
            # If generator didn't yield, we're not calling the next in the chain
            return

        next_handler(context)

        try:
            gen.next()
        except StopIteration:
            # Expected - nothing to yield
            return
        else:
            # Found another yield, which doesn't make sense
            raise RuntimeError("handler didn't stop")
    return wrapper


class Stack(object):
    def __init__(self, handlers=None):
        self.handlers = handlers or []

    def __call__(self, context, next=None):
        '''
        Supports chaining,
        so that a stack of handlers can be
        re-used.

        ex:

        auth = auth_wrapper()
        caching = caching_wrapper()
        logging = logging_wrapper()
        defaultStack = Stack([auth, caching, logging])

        custom1 = CustomLayer()
        custom2 = CustomLayer()
        customStack = Stack([custom1, custom2])

        appStack = Stack([defaultStack, customStack])
        '''
        self.__index = -1
        self.execute(context)
        if next:
            next(context)

    def execute(self, context):
        self.__index += 1

        # End of the chain
        if self.__index >= len(self.handlers):
            return

        self.handlers[self.__index](context, self.execute)
