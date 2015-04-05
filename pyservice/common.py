import builtins
import ujson


DEFAULT_API = {
    "version": "0",
    "timeout": 3,
    "debug": False,
    "endpoint": {
        "scheme": "https",
        "host": "localhost",
        "port": 8080,
        "path": "/api/{version}/{operation}"
    },
    "operations": [],
    "exceptions": []
}


def update_missing(src, dst):
    """Like `dict.update` but existing keys are not overwritten"""
    for key, value in src.items():
        dst[key] = dst.get(key, value)


def deserialize(string, container):
    """Load string as dict into container"""
    container.update(ujson.loads(string))


def serialize(container):
    """Dump container into string"""
    return ujson.dumps(container)


class Container(dict):
    """
    Allows attribute access to members, as well as index access.  Missing keys
    return None - missing values are not populated.

    >>> o = object()
    >>> c = Container()
    >>> c.key = o
    >>> assert c["key"] is c.key
    """

    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__
    __missing__ = lambda s, k: None


class Context(Container):
    """
    Available during requests, provides a dumping ground for plugins to
    store objects, such as database handles or shared caches.

    Plugins can execute code before and after the rest of the request is
    executed.  To continue processing the request, use
    `context.process_request()`.  This MUST NOT be called more than once in
    a single plugin.  To discontinue processing the request (ie. for caching)
    simply do not invoke `process_request()`.
    """
    def __init__(self, operation, processor):
        self.operation = operation
        self.__processor__ = processor

    def process_request(self):
        self.__processor__.continue_execution()


class ExceptionFactory(object):
    """
    Class for building and storing Exception types.
    Built-in exception names are reserved.

    Constructed classes are cached to keep types consistent across calls.
    >>> ex = ExceptionFactory()
    >>> ex.BadFoo is ex.BadFoo
    """
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

    def __getattr__(self, name):
        return self.get_class(name)
