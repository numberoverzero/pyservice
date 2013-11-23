import six

BUILTIN_EXCEPTIONS = [
"ArithmeticError",
"AssertionError",
"AttributeError",
"BaseException",
"BufferError",
"BytesWarning",
"DeprecationWarning",
"EOFError",
"EnvironmentError",
"Exception",
"FloatingPointError",
"FutureWarning",
"GeneratorExit",
"IOError",
"ImportError",
"ImportWarning",
"IndentationError",
"IndexError",
"KeyError",
"KeyboardInterrupt",
"LookupError",
"MemoryError",
"NameError",
"NotImplemented",
"NotImplementedError",
"OSError",
"OverflowError",
"PendingDeprecationWarning",
"ReferenceError",
"RuntimeError",
"RuntimeWarning",
"StandardError",
"StopIteration",
"SyntaxError",
"SyntaxWarning",
"SystemError",
"SystemExit",
"TabError",
"TypeError",
"UnboundLocalError",
"UnicodeDecodeError",
"UnicodeEncodeError",
"UnicodeError",
"UnicodeTranslateError",
"UnicodeWarning",
"UserWarning",
"ValueError",
"Warning",
"ZeroDivisionError",
]


class ExceptionFactory(object):
    def __init__(self):
        self._exceptions = {}

    def _build_exception(self, name):
        ex_cls = self._exceptions[name] = type(name, (Exception,), {})
        return ex_cls

    def exception(self, name, *args):
        return self.exception_cls(name)(*args)

    def exception_cls(self, name):
        if name not in BUILTIN_EXCEPTIONS:
            ex_cls = self._exceptions.get(name, None)
            if not ex_cls:
                ex_cls = self._build_exception(name)
        else:
            ex_cls = getattr(six.moves.builtins, name, None)
            # maybe the exception class was deleted? Who knows
            if not ex_cls:
                raise NameError("global name '{}' is not defined".format(name))
        return ex_cls


class ExceptionContainer(object):
    '''
    Usage:
        exceptions = ExceptionContainer()
        try:
            ...
        except exceptions.KeyError as e:
            print e.args
        except exceptions.SomeException as e:
            print e.args
    '''
    def __init__(self):
        self._factory = ExceptionFactory()
    def __getattr__(self, name):
        return self._factory.exception_cls(name)
