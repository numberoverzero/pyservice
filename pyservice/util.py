class cached_property(property):
    '''
    Very basic descriptor -
    caches results of get in the obj's __dict__
    and then returns that value forever.

    set, delete not supported.

    WARNING: This decorator is fragile, and uses the
    decorated function's name as the cache key.
    This means that if `other_decorator` is also a property,
    the following will not work:

        @cached_property
        @other_decorator
        def foo(self):
            ...

        @cached_property
        @other_decorator
        def bar(self):
            ...

    since other_decorator doesn't have a __name__ attribute
    '''

    def __get__(self, obj, objtype=None):
            if obj is None:
                    return self
            if not self.fget:
                    raise AttributeError("self.fget is not defined")

            key = self.fget.__name__
            if key not in obj.__dict__:
                value = self.fget(obj)
                obj.__dict__[key] = value
            return obj.__dict__[key]

    def __set__(self, obj, value):
        raise AttributeError("Can't set attribute")

    def __delete__(self, obj):
        raise AttributeError("Can't delete attribute")
