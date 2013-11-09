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
    my_service = pyservice.Service.from_json(junk_json)
    assert len(my_service.operations) == 0

def test_from_filename():
    filename = os.path.join(here, "BeerService.json")
    my_service = pyservice.Service.from_file(filename)
    assert len(my_service.operations) == 3

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

def test_decorated_function_returns_original():
    data = j('{"name": "ServiceName", "operations": [{"name":"ConcatOperation", "input": ["a", "b"], "output": ["ab"]}]}')
    service = pyservice.Service("ServiceName")
    pyservice.parse_service(service, data)

    def concat(a, b):
        return a + b

    original_func = concat
    wrapped_func = service.operation("ConcatOperation")(concat)
    assert original_func is wrapped_func
