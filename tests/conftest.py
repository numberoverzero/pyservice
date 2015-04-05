import pytest


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
