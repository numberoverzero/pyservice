import os
import json
import pytest

import pyservice

j = json.loads

#For loading relative files
here = os.path.dirname(os.path.realpath(__file__))

def test_invalid_name():
    with pytest.raises(ValueError):
        pyservice.Service("_invalid_leading_underscore")

def test_bad_json():
    not_json = "bad_json"
    with pytest.raises(TypeError):
        pyservice.Service.from_json(not_json)

def test_empty_service():
    junk_string = '{"name": "foo", "operations": []}'
    junk_json = json.loads(junk_string)
    service = pyservice.Service.from_json(junk_json)
    assert len(service.operations) == 0
    assert service._mapped

def test_from_filename():
    filename = os.path.join(here, "BeerService.json")
    service = pyservice.Service.from_file(filename)
    assert len(service.operations) == 3
    assert not service._mapped

def test_register_operation_twice():
    service = pyservice.Service("ServiceName")
    pyservice.Operation(service, "DuplicateOperation", [], [])
    with pytest.raises(KeyError):
        pyservice.Operation(service, "DuplicateOperation", [], [])

def test_register_exception_twice():
    service = pyservice.Service("ServiceName")
    class DummyException(pyservice.ServiceException): pass
    service._register_exception(DummyException)
    service._register_exception(DummyException)

def test_basic_exceptions_registered():
    service = pyservice.Service("ServiceName")
    assert pyservice.ServiceException in service.exceptions
    assert pyservice.ServerException in service.exceptions
    assert pyservice.ClientException in service.exceptions

def test_config():
    service = pyservice.Service("ServiceName")
    app_config = service._app.config
    service_config = service._config
    assert app_config is service_config

def test_full_operation_decorator():
    data = j('{"name": "ServiceName", "operations": [{"name":"CreateOperation", "input": ["arg1"]}]}')
    service = pyservice.parse_service(data)

    @service.operation("CreateOperation")
    def create(arg1): pass

    assert service._mapped

def test_partial_operation_decorator():
    data = j('{"name": "ServiceName", "operations": [{"name":"create", "input": ["arg1"]}]}')
    service = pyservice.parse_service(data)

    @service.operation
    def create(arg1): pass

    assert service._mapped

def test_direct_call_operation_decorator():
    data = j('{"name": "ServiceName", "operations": [{"name":"CreateOperation", "input": ["arg1"]}]}')
    service = pyservice.parse_service(data)
    def create(arg1): pass

    service.operation("CreateOperation", create)

    assert service._mapped

def test_decorated_function_returns_original():
    data = j('{"name": "ServiceName", "operations": [{"name":"ConcatOperation", "input": ["a", "b"], "output": ["ab"]}]}')
    service = pyservice.parse_service(data)

    def concat(a, b):
        return a + b

    original_func = concat
    wrapped_func = service.operation("ConcatOperation")(concat)
    assert original_func is wrapped_func
    assert service._mapped

def test_run_without_mapping():
    data = j('{"name": "ServiceName", "operations": [{"name":"ConcatOperation", "input": ["a", "b"], "output": ["ab"]}]}')
    service = pyservice.parse_service(data)

    assert not service._mapped
    with pytest.raises(ValueError):
        service.run()

def test_run_invokes_app_run():
    data = j('{"name": "ServiceName", "operations": []}')
    service = pyservice.parse_service(data)

    # Mock the service app since we just care that it's invoked with the same kwargs
    class App(object):
        def __init__(self, **passed_kwargs):
            self.passed_kwargs = passed_kwargs
        def run(self, **kwargs):
            assert kwargs == self.passed_kwargs

    kwargs = {
        "arg1": "Hello",
        "arg2": 2,
        "arg3": [0, 1, 2]
    }
    app = App(**kwargs)
    service._app = app
    service.run(**kwargs)
