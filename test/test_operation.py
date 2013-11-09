import json
import pytest
import collections

import pyservice

j = json.loads

def test_route():
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")
    assert operation.route == "/ServiceName/CreateOperation"

def test_registration():
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")
    assert "CreateOperation" in service.operations
    assert service.operations["CreateOperation"] is operation

def test_wrap_two_functions():
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")

    with pytest.raises(ValueError):
        def create(): pass
        def another_create(): pass
        operation.wrap(create)
        operation.wrap(another_create)

def test_wrap_function_twice():
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")

    with pytest.raises(ValueError):
        def create(): pass
        operation.wrap(create)
        operation.wrap(create)

def test_wrap_args():
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")

    with pytest.raises(ValueError):
        def create(*args): pass
        operation.wrap(create)

def test_wrap_kwargs():
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")

    with pytest.raises(ValueError):
        def create(**kwargs): pass
        operation.wrap(create)

def test_wrap_too_many_args():
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")

    with pytest.raises(ValueError):
        def create(a, b, c): pass
        operation.wrap(create)

def test_wrap_too_few_args():
    data = j('{"name":"CreateOperation", "input": ["a", "b"]}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")
    pyservice.parse_operation(service, operation, data)

    with pytest.raises(ValueError):
        def create(a): pass
        operation.wrap(create)

def test_wrap_arg_name_mismatch():
    data = j('{"name":"CreateOperation", "input": ["a", "b"]}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")
    pyservice.parse_operation(service, operation, data)

    with pytest.raises(ValueError):
        def create(alpha, beta): pass
        operation.wrap(create)

def test_wrap_no_input():
    data = j('{"name":"CreateOperation", "input": []}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")
    pyservice.parse_operation(service, operation, data)

    def create(): pass
    operation.wrap(create)

def test_build_input_ordering():
    data = j('{"name":"CreateOperation", "input": ["a", "b", "c"]}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")
    pyservice.parse_operation(service, operation, data)
    operation.wrap(lambda a, b, c: None)

    # Explicitly pass args out of order to make sure
    # we're not taking advantage of dict hashing
    # when iterating keys to build args
    inp = collections.OrderedDict([
        ("b", "World"),
        ("c", "!"),
        ("a", "Hello")
    ])
    args = operation.build_input(inp)
    assert args == ["Hello", "World", "!"]

def test_build_input_without_wrapping():
    data = j('{"name":"CreateOperation", "input": ["a", "b"]}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")
    pyservice.parse_operation(service, operation, data)

    inp = {
        "a": "Hello"
    }
    with pytest.raises(pyservice.ServiceException):
        operation.build_input(inp)

def test_build_input_no_args():
    data = j('{"name":"CreateOperation", "input": []}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")
    pyservice.parse_operation(service, operation, data)
    operation.wrap(lambda: None)

    inp = {}
    args = operation.build_input(inp)
    assert args == []

def test_build_input_too_few_args():
    data = j('{"name":"CreateOperation", "input": ["a", "b"]}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")
    pyservice.parse_operation(service, operation, data)
    operation.wrap(lambda a, b: None)

    inp = {
        "a": "Hello"
    }
    with pytest.raises(pyservice.ServiceException):
        operation.build_input(inp)

def test_build_input_too_many_args():
    data = j('{"name":"CreateOperation", "input": ["a", "b"]}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")
    pyservice.parse_operation(service, operation, data)
    operation.wrap(lambda a, b: None)

    inp = {
        "a": "Hello",
        "b": "World",
        "c": "!"
    }
    with pytest.raises(pyservice.ServiceException):
        operation.build_input(inp)

def test_build_input_wrong_args():
    data = j('{"name":"CreateOperation", "input": ["a", "b"]}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")
    pyservice.parse_operation(service, operation, data)
    operation.wrap(lambda a, b: None)

    inp = {
        "wrong": "Hello",
        "keys": "World",
    }
    with pytest.raises(pyservice.ServiceException):
        operation.build_input(inp)


def test_build_output_too_few_args():
    data = j('{"name":"CreateOperation", "output": ["a", "b"]}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")
    pyservice.parse_operation(service, operation, data)

    out = ["Hello"]
    with pytest.raises(pyservice.ServiceException):
        operation.build_output(out)

def test_build_output_too_many_args():
    data = j('{"name":"CreateOperation", "output": ["a", "b"]}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")
    pyservice.parse_operation(service, operation, data)

    out = ["Hello", "World", "!"]
    with pytest.raises(pyservice.ServiceException):
        operation.build_output(out)

def test_build_output_ordering():
    data = j('{"name":"CreateOperation", "output": ["a", "b"]}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")
    pyservice.parse_operation(service, operation, data)

    out = ["Hello", "World"]
    result = operation.build_output(out)
    assert result == {"a": "Hello", "b": "World"}

def test_build_output_no_args():
    data = j('{"name":"CreateOperation", "output": []}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")
    pyservice.parse_operation(service, operation, data)

    out = []
    result = operation.build_output(out)
    assert result == {}

def test_wrapped_func_returns_original():
    data = j('{"name":"ConcatOperation", "input": ["a", "b"], "output": ["ab"]}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "ConcatOperation")
    pyservice.parse_operation(service, operation, data)

    def concat(a, b):
        return a + b

    original_func = concat
    wrapped_func = operation.wrap(concat)
    assert original_func is wrapped_func
