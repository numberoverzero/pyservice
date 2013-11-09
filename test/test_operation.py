import json
import pytest
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

def test_build_input_too_few_args():
    data = j('{"name":"CreateOperation", "input": ["a", "b"]}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")
    pyservice.parse_operation(service, operation, data)

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

    inp = {
        "a": "Hello"
    }
    with pytest.raises(pyservice.ServiceException):
        operation.build_output(inp)

def test_build_output_too_many_args():
    data = j('{"name":"CreateOperation", "output": ["a", "b"]}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")
    pyservice.parse_operation(service, operation, data)

    inp = {
        "a": "Hello",
        "b": "World",
        "c": "!"
    }
    with pytest.raises(pyservice.ServiceException):
        operation.build_output(inp)

def test_build_output_wrong_args():
    data = j('{"name":"CreateOperation", "output": ["a", "b"]}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")
    pyservice.parse_operation(service, operation, data)

    inp = {
        "wrong": "Hello",
        "keys": "World",
    }
    with pytest.raises(pyservice.ServiceException):
        operation.build_output(inp)
