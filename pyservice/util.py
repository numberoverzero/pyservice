class cached_property(property):
    '''
    Very basic descriptor -
    caches results of get in the obj's __dict__
    and then returns that value forever.

    fset, fdel not supported.
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
