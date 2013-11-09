import os
import json
import pytest
import pyservice

j = json.loads

#For loading relative files
here = os.path.dirname(os.path.realpath(__file__))

def test_bad_json():
    not_json = "bad_json"
    with pytest.raises(TypeError):
        pyservice.Service.from_json(not_json)

def test_empty_service():
    junk_string = '{"name": "foo", "operations": []}'
    junk_json = json.loads(junk_string)
    service = pyservice.Service.from_json(junk_json)
    assert len(service.operations) == 0
    assert service.mapped

def test_from_filename():
    filename = os.path.join(here, "BeerService.json")
    service = pyservice.Service.from_file(filename)
    assert len(service.operations) == 3
    assert not service.mapped

def test_duplicate_register():
    service = pyservice.Service("ServiceName")
    pyservice.Operation(service, "DuplicateOperation")
    with pytest.raises(KeyError):
        pyservice.Operation(service, "DuplicateOperation")

def test_operation_decorator():
    data = j('{"name": "ServiceName", "operations": [{"name":"CreateOperation", "input": ["arg1"]}]}')
    service = pyservice.Service("ServiceName")
    pyservice.parse_service(service, data)

    @service.operation("CreateOperation")
    def create(arg1): pass

    assert service.mapped

def test_decorated_function_returns_original():
    data = j('{"name": "ServiceName", "operations": [{"name":"ConcatOperation", "input": ["a", "b"], "output": ["ab"]}]}')
    service = pyservice.Service("ServiceName")
    pyservice.parse_service(service, data)

    def concat(a, b):
        return a + b

    original_func = concat
    wrapped_func = service.operation("ConcatOperation")(concat)
    assert original_func is wrapped_func
    assert service.mapped
