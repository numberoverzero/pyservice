import pytest
from contextlib import contextmanager

from pyservice.exception_factory import ExceptionFactory

def test_builtin_exception():
    name = "TypeError"
    args = [1, 2, 3]
    exception = ExceptionFactory().exception(name, *args)

    assert TypeError is exception.__class__
    assert args == list(exception.args)

def test_builtin_shadowing():
    name = "False"
    args = [1, 2, 3]
    exception = ExceptionFactory().exception(name, *args)

    assert name == exception.__class__.__name__
    assert None.__class__ is not exception.__class__
    assert args == list(exception.args)


def test_custom_exception():
    name = "CustomException"
    args = [1, 2, 3]
    other_args = [4, 5, 6]

    factory = ExceptionFactory()
    exception = factory.exception(name, *args)
    another_exception = factory.exception(name, *other_args)
    assert name == exception.__class__.__name__
    assert issubclass(exception.__class__, Exception)
    assert exception.__class__ is another_exception.__class__

def test_different_factories():
    name = "CustomException"
    args = [1, 2, 3]
    other_args = [4, 5, 6]

    factory = ExceptionFactory()
    another_factory = ExceptionFactory()

    exception = factory.exception(name, *args)
    another_exception = another_factory.exception(name, *other_args)

    assert exception.__class__.__name__ == another_exception.__class__.__name__
    assert exception.__class__ is not another_exception.__class__

def test_missing_builtin():
    '''This test messes with global modules - be careful when updating,
    as it currently deletes a built-in exception type and puts it back after
    testing.  Many things will break in unpredictable ways if the error
    is not properly re-added to __builtin__ after testing.'''


    name = "TypeError"
    args = [1, 2, 3]

    with removed_global(name):
        with pytest.raises(NameError):
            ExceptionFactory().exception(name, *args)


@contextmanager
def removed_global(name):
    from sys import modules
    builtin = modules['__builtin__']

    # Save object so we can put it back after the test
    obj = getattr(builtin, name)
    delattr(builtin, name)

    yield

    # Put the object back so other tests don't break
    setattr(builtin, name, obj)
