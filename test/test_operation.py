import json
import pytest
import collections

import pyservice

j = json.loads

def test_invalid_name():
    service = pyservice.Service("ServiceName")
    with pytest.raises(ValueError):
        pyservice.Operation(service, "_invalid_leading_underscore")

def test_route():
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")
    assert operation._route == "/ServiceName/CreateOperation"

def test_registration():
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")
    assert "CreateOperation" in service.operations
    assert service.operations["CreateOperation"] is operation
    assert not operation._mapped

def test_wrap_two_functions():
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")

    with pytest.raises(ValueError):
        def create(): pass
        def another_create(): pass
        operation._wrap(create)
        operation._wrap(another_create)

def test_wrap_function_twice():
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")

    with pytest.raises(ValueError):
        def create(): pass
        operation._wrap(create)
        operation._wrap(create)

def test_wrap_args():
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")

    with pytest.raises(ValueError):
        def create(*args): pass
        operation._wrap(create)

def test_wrap_kwargs():
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")

    with pytest.raises(ValueError):
        def create(**kwargs): pass
        operation._wrap(create)

def test_wrap_too_many_args():
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")

    with pytest.raises(ValueError):
        def create(a, b, c): pass
        operation._wrap(create)

def test_wrap_too_few_args():
    data = j('{"name":"CreateOperation", "input": ["a", "b"]}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.parse_operation(service, data)

    with pytest.raises(ValueError):
        def create(a): pass
        operation._wrap(create)

def test_wrap_arg_name_mismatch():
    data = j('{"name":"CreateOperation", "input": ["a", "b"]}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.parse_operation(service, data)

    with pytest.raises(ValueError):
        def create(alpha, beta): pass
        operation._wrap(create)

def test_wrap_no_input():
    data = j('{"name":"CreateOperation", "input": []}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.parse_operation(service, data)

    def create(): pass
    operation._wrap(create)

def test_build_input_ordering():
    data = j('{"name":"CreateOperation", "input": ["a", "b", "c"]}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.parse_operation(service, data)
    operation._wrap(lambda a, b, c: None)

    # Explicitly pass args out of order to make sure
    # we're not taking advantage of dict hashing
    # when iterating keys to build args
    inp = collections.OrderedDict([
        ("b", "World"),
        ("c", "!"),
        ("a", "Hello")
    ])
    args = operation._build_input(inp)
    assert args == ["Hello", "World", "!"]

def test_build_input_without_wrapping():
    data = j('{"name":"CreateOperation", "input": ["a", "b"]}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.parse_operation(service, data)

    inp = {
        "a": "Hello"
    }
    with pytest.raises(pyservice.ClientException):
        operation._build_input(inp)

def test_build_input_no_args():
    data = j('{"name":"CreateOperation", "input": []}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.parse_operation(service, data)
    operation._wrap(lambda: None)

    inp = {}
    args = operation._build_input(inp)
    assert args == []

def test_build_input_too_few_args():
    data = j('{"name":"CreateOperation", "input": ["a", "b"]}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.parse_operation(service, data)
    operation._wrap(lambda a, b: None)

    inp = {
        "a": "Hello"
    }
    with pytest.raises(pyservice.ClientException):
        operation._build_input(inp)

def test_build_input_too_many_args():
    data = j('{"name":"CreateOperation", "input": ["a", "b"]}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.parse_operation(service, data)
    operation._wrap(lambda a, b: None)

    inp = {
        "a": "Hello",
        "b": "World",
        "c": "!"
    }
    with pytest.raises(pyservice.ClientException):
        operation._build_input(inp)

def test_build_input_wrong_args():
    data = j('{"name":"CreateOperation", "input": ["a", "b"]}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.parse_operation(service, data)
    operation._wrap(lambda a, b: None)

    inp = {
        "wrong": "Hello",
        "keys": "World",
    }
    with pytest.raises(pyservice.ClientException):
        operation._build_input(inp)


def test_build_output_too_few_args():
    data = j('{"name":"CreateOperation", "output": ["a", "b"]}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.parse_operation(service, data)

    out = ["Hello"]
    with pytest.raises(pyservice.ServerException):
        operation._build_output(out)

def test_build_output_too_many_args():
    data = j('{"name":"CreateOperation", "output": ["a", "b"]}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.parse_operation(service, data)

    out = ["Hello", "World", "!"]
    with pytest.raises(pyservice.ServerException):
        operation._build_output(out)

def test_build_output_ordering():
    data = j('{"name":"CreateOperation", "output": ["a", "b"]}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.parse_operation(service, data)

    out = ["Hello", "World"]
    result = operation._build_output(out)
    assert result == {"a": "Hello", "b": "World"}

def test_build_output_no_args():
    data = j('{"name":"CreateOperation", "output": []}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.parse_operation(service, data)

    out = []
    result = operation._build_output(out)
    assert result == {}

def test_wrapped_func_returns_original():
    data = j('{"name":"ConcatOperation", "input": ["a", "b"], "output": ["ab"]}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.parse_operation(service, data)

    def concat(a, b):
        return a + b

    original_func = concat
    wrapped_func = operation._wrap(concat)
    assert original_func is wrapped_func
    assert operation._mapped
