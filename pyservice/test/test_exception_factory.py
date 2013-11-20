import pytest

from pyservice import exception_factory

def test_builtin_exception():
    name = "TypeError"
    args = [1, 2, 3]
    exception = exception_factory.builtin_exception(name, *args)

    assert name == exception.__class__.__name__
    assert args == list(exception.args)

def test_builtin_non_exception():
    name = "False"
    args = [1, 2, 3]
    with pytest.raises(NameError):
        exception_factory.builtin_exception(name, *args)

def test_builtin_unknown_exception():
    name = "NotARealException"
    args = [1, 2, 3]
    with pytest.raises(NameError):
        exception_factory.builtin_exception(name, *args)
