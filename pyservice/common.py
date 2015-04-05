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
    """
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
    """
    fmt = "{scheme}://{host}:{port}{pattern}"
    try:
        endpoint["client_pattern"] = fmt.format(**endpoint)
    except KeyError as exception:
        missing_key = exception.args[0]
        raise ValueError("endpoint must specify '{}'".format(missing_key))


def construct_service_pattern(endpoint):
    """
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
    """
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
    Enable attribute access to dict keys.

    Missing keys return None, and are not persisted.
    dict methods can be overwritten (container.keys = "foo" is fine)

    >>> o = object()
    >>> c = Container()
    >>> c.keys = o
    >>> assert c["keys"] is c.keys
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # For more info on this magic: http://stackoverflow.com/a/14620633
        self.__dict__ = self

    def __getattr__(self, key):
        # We can't use __missing__ here because the `__dict__ = self`
        # above will cause KeyErrors and never call __missing__.
        return None


class Context:
    """
    Available during requests, provides a dumping ground for plugins to
    store objects, such as database handles or shared caches.

    Attributes:

    operation - (string) name of the current operation
    client - (Client) only available during the client portion of a request
    service - (Service) only available during the service portion of a request


    Plugins can execute code before and after the rest of the request is
    executed.  To continue processing the request, use
        `context.process_request()`.
    This MUST NOT be called more than once in a single plugin.
    To discontinue processing the request (ie. for caching)
    simply do not invoke `process_request()`.
    """
    def __init__(self, processor):
        self.__processor__ = processor

    def process_request(self):
        """
        Continue processing the request.

        Either invokes the next plugin or hands the request off to the
        remote endpoint (client context) or the underlying function
        (service context)
        """
        self.__processor__.continue_execution()


class ExceptionFactory(object):
    """
    Class for building and storing Exception types.
    Built-in exception names are reserved.

    Constructed classes are cached to keep types consistent across calls.
    >>> ex = ExceptionFactory()
    >>> ex.BadFoo is ex.BadFoo
    >>> ex.ValueError is ValueError
    """

    def __build__(self, name):
        return type(name, (Exception,), {})

    def __getattr__(self, name):
        # Check builtins for real exception class
        cls = getattr(builtins, name, None)

        # Not builtin, create the class
        cls = cls or self.__build__(name)

        # Cache the result so we skip the getattr overhead next time
        setattr(self, name, cls)

        return cls
