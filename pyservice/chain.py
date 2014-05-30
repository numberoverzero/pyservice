"""
# First argument to the function should be the next
# object to invoke (next_handler below)

class EventHandler(object):
    def __init__(self, name):
        self.name = name

    def handle(self, next_handler, event, data):
        print("ENTER: Handler {} Event {}".format(self.name, event))
        next_foo(value)
        print("EXIT: Handler {} Event {}".format(self.name, event))

handlers = [
    EventHandler("ip_throttle"),
    EventHandler("metrics"),
    EventHandler("auth"),
    EventHandler("auth_throttle"),
    EventHandler("cache")
    # Function invoked here
]

# Create a chain for invoking any function
# or for a single function
handlers_chain = chain(handlers)
fire = chain(handlers, 'handle')

# Push a single event
data = {'config': 'value'}

handlers_chain.handle("init", data)
fire("init", data)
"""

import functools
_noop = lambda *a, **kw: None


def _compile(objs, method):
    _next = _noop
    for obj in reversed(objs):
        func = getattr(obj, method, None)
        if func:
            _next = functools.partial(func, _next)
    return _next


class Chain(object):
    def __init__(self, objs):
        # Private to avoid clashes when we setattr after compiling
        self.__objs = objs

    def __getattr__(self, name):
        # Bind the compiled partial to self so we avoid
        # __getattr__ overhead on the next call
        func = _compile(self.__objs, name)
        setattr(self, name, func)
        return func


def chain(objs, method_name=None):
    '''
    Pass a method name to create a fixed chain for a single method
    on the set of objects, or pass None to get a Chain that will
    create nested function calls for any method
    '''
    c = Chain(objs)
    if method_name:
        return getattr(c, method_name)
    return c
