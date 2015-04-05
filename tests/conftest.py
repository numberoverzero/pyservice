import pytest


@pytest.fixture
def observe(monkeypatch):
    def patch(module, func):
        original_func = getattr(module, func)

        def wrapper(*args, **kwargs):
            result = original_func(*args, **kwargs)
            self.calls[self.last_call] = (args, kwargs, result)
            self.last_call += 1
            return result

        self = wrapper
        self.calls = {}
        self.last_call = 0
        monkeypatch.setattr(module, func, wrapper)
        return wrapper
    return patch
