import os
import json
import pytest
import webtest

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
    service._register_exception("DummyException", DummyException)
    with pytest.raises(KeyError):
        service._register_exception("DummyException", DummyException)

def test_reregister_builtin_exception():
    service = pyservice.Service("ServiceName")
    class DummyException(pyservice.ServiceException): pass
    with pytest.raises(KeyError):
        service._register_exception("ServiceException", DummyException)

def test_basic_exceptions_registered():
    service = pyservice.Service("ServiceName")
    assert service.exceptions["ServiceException"] is pyservice.ServiceException
    assert service.exceptions["ServerException"] is pyservice.ServerException
    assert service.exceptions["ClientException"] is pyservice.ClientException

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

def test_raise_builtin_exception():
    service = pyservice.Service("ServiceName")
    with pytest.raises(pyservice.ClientException):
        service.raise_("ClientException", "message")

def test_raise_registered_exception():
    service = pyservice.Service("ServiceName")
    class MyException(Exception): pass
    service._register_exception("MyException", MyException)

    with pytest.raises(MyException):
        service.raise_("MyException", "message")

def test_raise_unknown_exception():
    service = pyservice.Service("ServiceName")
    class MyException(Exception): pass

    with pytest.raises(pyservice.ServerException):
        service.raise_("MyException", "message")

def test_event_ordering():
    class OrderingLayer(pyservice.Layer):
        events = []
        def on_input(self, context):
            OrderingLayer.events.append("input")
        def on_output(self, context):
            OrderingLayer.events.append("output")
        @property
        def validate(self):
            assert OrderingLayer.events == ["input", "output"]

    data = j('{"name": "ServiceName", "operations": [{"name":"noop", "input": [], "output": []}]}')
    service = pyservice.parse_service(data)
    operation = service.operations["noop"]
    @service.operation("noop")
    def concat():
        return None

    layer = OrderingLayer(service)
    assert concat
    assert not pyservice.handle_request(service, operation, concat, {})
    assert layer.on_input in service._handlers['on_input']
    assert layer.on_output in service._handlers['on_output']

    #layer.validate
