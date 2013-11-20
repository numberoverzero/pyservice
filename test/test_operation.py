import json
import pytest

from pyservice.service import Service
from pyservice.operation import Operation, parse_operation

j = json.loads

def test_invalid_name():
    service = Service("ServiceName")
    with pytest.raises(ValueError):
        Operation(service, "_invalid_leading_underscore", [], [])

def test_route():
    service = Service("ServiceName")
    operation = Operation(service, "CreateOperation", [], [])
    assert operation._route == "/ServiceName/CreateOperation"

def test_registration():
    service = Service("ServiceName")
    operation = Operation(service, "CreateOperation", [], [])
    assert "CreateOperation" in service.operations
    assert service.operations["CreateOperation"] is operation
    assert not operation._mapped

def test_wrap_two_functions():
    service = Service("ServiceName")
    operation = Operation(service, "CreateOperation", [], [])

    with pytest.raises(ValueError):
        def create(): pass
        def another_create(): pass
        operation._wrap(create)
        operation._wrap(another_create)

def test_wrap_function_twice():
    service = Service("ServiceName")
    operation = Operation(service, "CreateOperation", [], [])

    with pytest.raises(ValueError):
        def create(): pass
        operation._wrap(create)
        operation._wrap(create)

def test_wrap_args():
    service = Service("ServiceName")
    operation = Operation(service, "CreateOperation", [], [])

    with pytest.raises(ValueError):
        def create(*args): pass
        operation._wrap(create)

def test_wrap_kwargs():
    service = Service("ServiceName")
    operation = Operation(service, "CreateOperation", [], [])

    with pytest.raises(ValueError):
        def create(**kwargs): pass
        operation._wrap(create)

def test_wrap_too_many_args():
    service = Service("ServiceName")
    operation = Operation(service, "CreateOperation", [], [])

    with pytest.raises(ValueError):
        def create(a, b, c): pass
        operation._wrap(create)

def test_wrap_too_few_args():
    data = j('{"name":"CreateOperation", "input": ["a", "b"]}')
    service = Service("ServiceName")
    operation = parse_operation(service, data)

    with pytest.raises(ValueError):
        def create(a): pass
        operation._wrap(create)

def test_wrap_arg_name_mismatch():
    data = j('{"name":"CreateOperation", "input": ["a", "b"]}')
    service = Service("ServiceName")
    operation = parse_operation(service, data)

    with pytest.raises(ValueError):
        def create(alpha, beta): pass
        operation._wrap(create)

def test_wrap_no_input():
    data = j('{"name":"CreateOperation", "input": []}')
    service = Service("ServiceName")
    operation = parse_operation(service, data)

    def create(): pass
    operation._wrap(create)

def test_wrapped_func_returns_original():
    data = j('{"name":"ConcatOperation", "input": ["a", "b"], "output": ["ab"]}')
    service = Service("ServiceName")
    operation = parse_operation(service, data)

    def concat(a, b):
        return a + b

    original_func = concat
    wrapped_func = operation._wrap(concat)
    assert original_func is wrapped_func
    assert operation._mapped
