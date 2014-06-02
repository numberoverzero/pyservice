"""
class EventHandler(object):
    def handle(self, next_handler, event, data):
        print("ENTER: Handler {} Event {}".format(event))
        next_handler(event, data)
        print("EXIT: Handler {} Event {}".format(event))

handlers = [EventHandler(), EventHandler()]
data = {'config': 'value'}

handlers_chain = chain(handlers)
handlers_chain.handle("init", data)

fire = chain(handlers, 'handle')
fire("init", data)
"""
import functools


class Chain(object):
    __noop = lambda *a, **kw: None

    def __init__(self, objs):
        # Private to avoid clashes when we setattr after compiling
        self.__objs = objs
        self.__call_partial = None

    def __compile(self, method):
        _next = self.__noop
        for obj in reversed(self.__objs):
            func = getattr(obj, method, None)
            if func:
                _next = functools.partial(func, _next)
        return _next

    def __getattr__(self, name):
        # Bind the compiled partial to self so we avoid
        # __getattr__ overhead on the next call
        func = self.__compile(name)
        setattr(self, name, func)
        return func

    def __call__(self, *args, **kwargs):
        '''special case because __getattr__ does not handle __call__'''
        if not self.__call_partial:
            self.__call_partial = self.__compile('__call__')
        return self.__call_partial(*args, **kwargs)
