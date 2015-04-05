import builtins
import copy
import re
import ujson


DEFAULT_API = {
    "version": "0",
    "timeout": 3,
    "debug": False,
    "endpoint": {
        "scheme": "http",
        "pattern": "/api/{operation}",
        "host": "localhost",
        "port": 8080
    },
    "operations": [],
    "exceptions": []
}


def load_defaults(api):
    """ Update the given api (nested dict) with any missing values """
    default = copy.deepcopy(DEFAULT_API)
    for key, default_value in default.items():
        api[key] = api.get(key, default_value)


def construct_client_pattern(endpoint):
    '''
    Build a format string that operation name can be substituted into,
    and store it in the given endpoint dictionary.

    Input:
        {
            scheme: http,
            host: foohost,
            port: 8888,
            pattern: /api/{operation}
        }

    Output:
        {
            scheme: http,
            host: foohost,
            port: 8888,
            pattern: /api/{operation},
            client_pattern: http://foohost:8888/api/{operation}
        }
    '''
    fmt = "{scheme}://{host}:{port}{pattern}"
    try:
        endpoint["client_pattern"] = fmt.format(**endpoint)
    except KeyError as exception:
        missing_key = exception.args[0]
        raise ValueError("endpoint must specify '{}'".format(missing_key))


def construct_service_pattern(endpoint):
    '''
    Build a regex for comparing environ['PATH_INFO'] to,
    and store it in the given endpoint dictionary.

    Input:
        {
            scheme: http,
            host: foohost,
            port: 8888,
            pattern: /api/{operation}
        }

    Output:
        {
            scheme: http,
            host: foohost,
            port: 8888,
            pattern: /api/{operation},
            service_pattern: re.compile('^/api/(?P<operation>[^/]+)/?$')
        }
    '''
    # Replace {operation} so that we can route an incoming request
    # Ignore trailing slash - /foo/ and /foo are identical
    try:
        pattern = endpoint["pattern"].format(operation="(?P<operation>[^/]+)")
    except KeyError:
        raise ValueError("endpoint must specify 'pattern'")
    operation_regex = re.compile("^{}/?$".format(pattern))
    endpoint["service_pattern"] = operation_regex


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
