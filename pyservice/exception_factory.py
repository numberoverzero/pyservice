import builtins


class ExceptionFactory(object):
    '''
    Class for building and storing Exception types.
    Built-in exception names are reserved.
    '''
    def __init__(self):
        self.classes = {}

    def build_exception_class(self, name):
        self.classes[name] = type(name, (Exception,), {})
        return self.classes[name]

    def get_class(self, name):
        # Check builtins for real exception class
        cls = getattr(builtins, name, None)
        # Cached?
        if not cls:
            cls = self.classes.get(name, None)
        # Cache
        if not cls:
            cls = self.build_exception_class(name)
        return cls

    def exception(self, name, *args):
        return self.get_class(name)(*args)


class ExceptionContainer(object):
    '''
    Usage:
        exceptions = ExceptionContainer()
        assert KeyError is exceptions.KeyError

        try:
            ...
        except exceptions.KeyError as e:
            print e.args
        except exceptions.SomeException as e:
            print e.args
    '''
    def __init__(self):
        self.factory = ExceptionFactory()

    def __getattr__(self, name):
        return self.factory.get_class(name)
