import pytest
import pyservice

def test_operation_route():
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")
    assert operation.route == "/ServiceName/CreateOperation"

def test_operation_registration():
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")
    assert "CreateOperation" in service.operations
    assert service.operations["CreateOperation"] is operation

def test_operation_wrap_two_functions():
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")
    def create():
        pass
    def another_create():
        pass
    operation.wrap(create)
    with pytest.raises(ValueError):
        operation.wrap(another_create)

def test_operation_wrap_function_twice():
    service = pyservice.Service("ServiceName")
    operation = pyservice.Operation(service, "CreateOperation")
    def create():
        pass
    operation.wrap(create)
    with pytest.raises(ValueError):
        operation.wrap(create)
