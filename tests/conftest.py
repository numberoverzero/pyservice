import pytest
import pyservice


@pytest.fixture
def api():
    ''' Very Simple API - no operations '''
    return {
        "endpoint": {
            "scheme": "http",
            "pattern": "/test/{operation}",
            "host": "localhost",
            "port": 8080
        },
        "operations": ["foo"]
    }


@pytest.fixture
def service(api):
    ''' Return a service with a simple api '''
    return pyservice.Service(**api)


@pytest.fixture
def start_response():
    ''' Function that stores status, headers on itself '''
    def func(status, headers):
        self.status = status
        self.headers = headers
    self = func
    return func


@pytest.fixture
def observe(monkeypatch):
    """
    Wrap a function so its call history can be inspected.

    Example:

    # foo.py
    def func(bar):
        return 2 * bar

    # test.py
    import pytest
    import foo

    def test_func(observe):
        observer = observe(foo, "func")
        assert foo.func(3) == 6
        assert foo.func(-5) == -10
        assert len(observer.calls) == 2
    """
    class ObserverFactory:
        def __init__(self, module, func):
            self.original_func = getattr(module, func)
            self.calls = []
            monkeypatch.setattr(module, func, self)

        def __call__(self, *args, **kwargs):
            result = self.original_func(*args, **kwargs)
            self.calls.append((args, kwargs, result))
            return result
    return ObserverFactory
