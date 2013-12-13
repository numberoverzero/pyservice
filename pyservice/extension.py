import types
import six
import sys

def extension(func):
    '''
    Creates an Extension that only overrides the handle_operation
    function.  use the 'yield' keyword to indicate where the rest
    of the operation handler chain should be invoked.

    Similar in usage to the @contextmanager decorator


    Typical usage:

        @extension
        def Logger(context):
            # Before the rest of the handlers execute
            start_time = time.now()

            #Process the operation
            yield

            # Log the operation timing
            end_time = time.now()

            msg = "Operation {} completed in {} seconds."
            name = context["operation"].name
            logger.info(msg.format(name, end_time - start_time))

        service = Service(some_description)
        logger = Logger(service)

    The rest of the handlers in a chain are executed when control is yielded
    '''
    class GeneratedExtension(Extension):
        def handle_operation(self, context, next_handler):
            # Before next handler
            gen = func(context)

            # If it's not a generator, don't execute the rest of the chain.
            # For whatever reason, the handler terminated the operation
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
                #   convenience for writing before/after blocks for operation handling.
                #   Therefore, we want to let any except/finally/else blocks in the
                #   extension run against whatever was raised in the chain.
                #
                # Why catch everything?
                #   Unlikely though it is, the extension may want to do something
                #   with BaseException.  It's a little weird that we're injecting
                #   the exception back into the generator, but we don't want to
                #   yield away from the extension, hit an exception down the chain,
                #   and bail from this helper, not letting the extension we're
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
                raise RuntimeError("extension didn't stop")
    return GeneratedExtension


class Extension(object):
    '''
    Service or Client extension - can add behavior before an operation starts,
    a handler during operation execution, and behavior after an operation returns
    '''
    def __init__(self, obj=None, **kwargs):
        '''
        Client/Service is optional.
        This allows the pattern:
            class Database(Extension):
                ...

            service = Service(description)
            database = Database(service)
            assert database in service._extensions
        '''
        self.obj = obj
        if self.obj:
            self.obj._register_extension(self)

    def before_operation(self, operation, next_handler):
        next_handler(operation)

    def handle_operation(self, context, next_handler):
        next_handler(context)

    def after_operation(self, operation, next_handler):
        next_handler(operation)


class ExtensionExecutor(object):
    def __init__(self, extensions):
        self.extensions = list(extensions)
        self.index = -1

    def before_operation(self, operation):
        self.index += 1
        if self.index >= len(self.extensions):
            return
        extension = self.extensions[self.index]
        extension.before_operation(operation, self.before_operation)

    def handle_operation(self, context):
        self.index += 1
        if self.index >= len(self.extensions):
            return
        extension = self.extensions[self.index]
        extension.handle_operation(context, self.handle_operation)

    def after_operation(self, operation):
        self.index += 1
        if self.index >= len(self.extensions):
            return
        extension = self.extensions[self.index]
        extension.after_operation(operation, self.after_operation)

def execute(extensions, method, *args):
    executor = ExtensionExecutor(extensions)
    func = getattr(executor, method)
    func(*args)
