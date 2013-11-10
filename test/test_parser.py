import json
import pyservice

j = json.loads

def test_parse_name():
    data = j('{"name": "ServiceName"}')
    assert pyservice.parse_name(data) == "ServiceName"

def test_parse_empty_service():
    data = j('{"name": "ServiceName"}')
    service = pyservice.parse_service(data)
    assert not service.operations

def test_parse_basic_service():
    data = j('{"name": "ServiceName", "operations": [{"name":"CreateOperation"}]}')
    service = pyservice.parse_service(data)
    assert len(service.operations) == 1

def test_parse_empty_operation():
    data = j('{"name":"CreateOperation"}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.parse_operation(service, data)
    assert not operation.input
    assert not operation.output

def test_parse_basic_operation():
    data = j('{"name":"CreateOperation", "input": ["in1", "in2", "in3"], "output": ["out1", "out2"]}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.parse_operation(service, data)
    assert set(operation.input) == set(["in1", "in2", "in3"])
    assert set(operation.output) == set(["out1", "out2"])

def test_parse_service_metadata():
    data = j('{"name": "ServiceName", "foo": ["bar"]}')
    service = pyservice.parse_service(data)
    assert "foo" in service.metadata
    assert service.metadata["foo"] == ["bar"]

def test_parse_operation_metadata():
    data = j('{"name": "CreateOperation", "foo": ["bar"]}')
    service = pyservice.Service("ServiceName")
    operation = pyservice.parse_operation(service, data)
    assert not service.metadata
    assert "foo" in operation.metadata
    assert operation.metadata["foo"] == ["bar"]
