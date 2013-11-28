import re
import six
import json
import pytest
import tempfile
import bottle
from contextlib import contextmanager
from collections import defaultdict

from pyservice.exception_factory import ExceptionFactory, ExceptionContainer
from pyservice.description import (
    validate_name,
    parse_metadata,
    default_field,
    Description,
    ServiceDescription,
    OperationDescription
)
from pyservice.layer import Layer, Stack
from pyservice.serialize import JsonSerializer, to_list, to_dict
from pyservice.util import cached, cached_property
from pyservice.client import Client
from pyservice.service import Service

#===========================
#
# Description helpers
#
#===========================

def test_validate_name():
    valid_names = [
        'b', 'B', 'contains_UNDERSCORES', 'trailing_'
    ]
    invalid_names = [
        '_', '_name', 'sy.mbol', '$wat', 'sp ace'
    ]
    for name in valid_names:
        validate_name(name)
    for name in invalid_names:
        with pytest.raises(ValueError):
            validate_name(name)

def test_parse_metadata_invalid_name():
    data = {
        "_invalid": "value"
    }
    with pytest.raises(ValueError):
        parse_metadata(data)

def test_parse_metadata_no_blacklist():
    data = {
        "foo": "value",
        "list": [""],
        "object": {"_nested_keys": "aren't validated"}
    }
    assert data == parse_metadata(data)

def test_parse_metadata_partial_blacklist():
    data = {
        "key": "not reserved",
        "other_key": ["also reserved"]
    }
    blacklist = ["other_key"]
    assert {"key": "not reserved"} == parse_metadata(data, blacklist)

def test_parse_metadata_all_blacklisted():
    data = {
        "key": "reserved",
        "other_key": ["also reserved"]
    }
    blacklist = ["key", "other_key"]
    assert {} == parse_metadata(data, blacklist)

def test_default_field_has_field():
    class Class(object):
        calls = 0
        def __init__(self):
            Class.calls += 1

    value = {0: 1}
    obj = { "name": value }
    field = "name"
    cls = Class
    value_out = default_field(obj, field, cls)
    assert value is value_out
    assert value is obj["name"]
    assert 0 == Class.calls

def test_default_field_does_not_have_field():
    class Class(object):
        calls = 0
        def __init__(self):
            Class.calls += 1

    obj = {}
    field = "name"
    cls = Class

    value_out = default_field(obj, field, cls)
    assert value_out is obj["name"]
    assert 1 == Class.calls

#===========================
#
# Description
#
#===========================

def test_description_no_name_attr():
    obj = {"invalid": "obj"}
    with pytest.raises(KeyError):
        Description(obj)

def test_description_has_name_attr():
    obj = {"name": "foo"}
    desc = Description(obj)
    assert desc._obj is obj
    assert desc.name == obj["name"]

def test_description_init_string():
    name = "foo"
    desc = Description(name)
    assert name == desc.name

def test_description_from_json():
    data = json.loads(valid_description_string().replace('\n', ''))
    desc = Description.from_json(data)
    assert "service" == desc.name
    assert data is not desc._obj

def test_description_from_string():
    string = valid_description_string()
    Description.from_string(string)

def test_description_from_file():
    with tempfile.NamedTemporaryFile(mode='w+') as file_obj:
        file_obj.write(valid_description_string())
        file_obj.seek(0)
        Description.from_file(file_obj.name)

def test_description_metadata_empty():
    return
    data = {"name": "name"}
    desc = Description(data)
    assert not desc.metadata

def test_description_metadata_reserved_fields_walk_classes():
    class MyDescription(Description):
        reserved_fields = ["foo"]

    data = {"name": "name", "foo": "foo"}
    desc = MyDescription(data)
    assert not desc.metadata

def test_description_metadata_extra_fields():
    data = {"name": "name", "key": "value"}
    desc = Description(data)
    assert {"key": "value"} == desc.metadata

#===========================
#
# OperationDescription
#
#===========================

def test_operation_description_no_name():
    data = {}
    with pytest.raises(KeyError):
        OperationDescription(data)

def test_operation_description_no_input_or_output():
    data = {"name": "operation"}
    operation = OperationDescription(data)
    assert not operation.input
    assert not operation.output

def test_operation_description_valid_input_formats():
    data = {
        "name": "operation",
        "input": [
            {
                "name": "input1"
            },
            "input2"
        ]
    }
    operation = OperationDescription(data)
    assert ["input1", "input2"] == [field.name for field in operation.input]
    assert all(isinstance(field, Description) for field in operation.input)

def test_operation_description_invalid_input():
    data = {
        "name": "operation",
        "input": [
            {
                "not_name_field": "bad"
            }
        ]
    }
    with pytest.raises(KeyError):
        OperationDescription(data)

def test_operation_description_valid_output_formats():
    data = {
        "name": "operation",
        "output": [
            {
                "name": "output1"
            },
            "output2"
        ]
    }
    operation = OperationDescription(data)
    assert ["output1", "output2"] == [field.name for field in operation.output]
    assert all(isinstance(field, Description) for field in operation.output)

def test_operation_description_invalid_output():
    data = {
        "name": "operation",
        "output": [
            {
                "not_name_field": "bad"
            }
        ]
    }
    with pytest.raises(KeyError):
        OperationDescription(data)

#===========================
#
# ServiceDescription
#
#===========================

def test_service_description_no_name():
    data = {}
    with pytest.raises(KeyError):
        ServiceDescription(data)

def test_service_description_no_operations_or_exceptions():
    data = {"name": "service"}
    service = ServiceDescription(data)
    assert not service.exceptions
    assert not service.operations

def test_service_description_valid_operation_formats():
    data = {
        "name": "service",
        "operations": [
            "operation1",
            {
                "name": "operation2"
            },
            {
                "name": "operation3",
                "input": ["input3_1"]
            },
            {
                "name": "operation4",
                "input": [
                    "input4_1",
                    {"name": "input4_2"}
                ]
            }
        ]
    }
    service = ServiceDescription(data)

    expected_operations = ["operation"+str(i) for i in [1,2,3,4]]
    assert set(expected_operations) == set(service.operations)

    assert not service.operations["operation1"].input
    assert not service.operations["operation2"].input
    assert ["input3_1"] == [field.name for field in service.operations["operation3"].input]
    assert ["input4_1", "input4_2"] == [field.name for field in service.operations["operation4"].input]

def test_service_description_valid_exceptions():
    data = {
        "name": "service",
        "exceptions": [
            "exception1",
            {
                "name": "exception2"
            }
        ]
    }
    service = ServiceDescription(data)

    expected_exceptions = ["exception1", "exception2"]
    assert set(expected_exceptions) == set(service.exceptions)

def test_full_description_metadata():
    string = valid_description_string()
    service = ServiceDescription.from_string(string)

    assert not service.metadata
    for name, operation in six.iteritems(service.operations):
        assert not operation.metadata
    for name, exception in six.iteritems(service.exceptions):
        assert not exception.metadata

#===========================
#
# Exception Factory
#
#===========================

def test_builtin_exception():
    name = "TypeError"
    args = [1, 2, 3]
    exception = ExceptionFactory().exception(name, *args)

    assert TypeError is exception.__class__
    assert args == list(exception.args)

def test_same_exception_class():
    name = "MyException"
    factory = ExceptionFactory()
    ex_cls1 = factory.exception_cls(name)
    ex_cls2 = factory.exception_cls(name)
    assert ex_cls1 is ex_cls2

def test_builtin_shadowing():
    name = "False"
    args = [1, 2, 3]
    exception = ExceptionFactory().exception(name, *args)

    assert name == exception.__class__.__name__
    assert None.__class__ is not exception.__class__
    assert args == list(exception.args)

def test_custom_exception():
    name = "CustomException"
    args = [1, 2, 3]

    factory = ExceptionFactory()
    exception = factory.exception(name, *args)
    assert name == exception.__class__.__name__
    assert issubclass(exception.__class__, Exception)

def test_different_exception_factories():
    name = "CustomException"
    args = [1, 2, 3]
    other_args = [4, 5, 6]

    factory = ExceptionFactory()
    another_factory = ExceptionFactory()

    exception = factory.exception(name, *args)
    another_exception = another_factory.exception(name, *other_args)

    assert exception.__class__.__name__ == another_exception.__class__.__name__
    assert exception.__class__ is not another_exception.__class__

def test_missing_builtin():
    name = "NameError"
    args = [1, 2, 3]

    RealNameError = NameError
    with removed_global(name):
        with pytest.raises(RealNameError):
            ExceptionFactory().exception(name, *args)

#===========================
#
# Exception Container
#
#===========================

def test_exception_container_builtin():
    exceptions = ExceptionContainer()
    assert KeyError is exceptions.KeyError
    assert exceptions.KeyError is exceptions.KeyError
    with pytest.raises(ValueError):
        raise exceptions.ValueError("Equivalent type")

def test_exception_container_custom():
    exceptions = ExceptionContainer()
    class MyException(Exception):
        pass
    assert MyException is not exceptions.MyException

    with pytest.raises(exceptions.PreviouslyUndefinedException):
        raise exceptions.PreviouslyUndefinedException()

    with pytest.raises(Exception):
        raise exceptions.BaseClassIsException()

#===========================
#
# Serializers
#
#===========================

def test_bad_deserialize():
    string = "{Malformed ] JSON"
    serializer = JsonSerializer()

    with pytest.raises(ValueError):
        serializer.deserialize(string)

def test_good_deserialize():
    string = '{"good": ["json"]}'
    serializer = JsonSerializer()
    serializer.deserialize(string)

def test_bad_serialize():
    # json can't serialize types
    data = {"bad": type}
    serializer = JsonSerializer()

    with pytest.raises(TypeError):
        serializer.serialize(data)

def test_good_serialize():
    data = {"good": ["json"]}
    expected = '{"good": ["json"]}'

    serializer = JsonSerializer()
    actual = serializer.serialize(data)

    assert expected == actual

#===========================
#
# dict --> list conversion
#
#===========================

def test_to_list_no_signature_exact():
    signature = []
    data = {}

    assert [] == to_list(signature, data)

def test_to_list_no_signature_extra():
    signature = []
    data = {"extra": "field"}

    assert [] == to_list(signature, data)

def test_to_list_one_field_no_data():
    signature = ["field"]
    data = {}

    with pytest.raises(KeyError):
        to_list(signature, data)

def test_to_list_one_field_exact():
    signature = ["field"]
    data = {"field": "value"}

    assert ["value"] == to_list(signature, data)

def test_to_list_one_field_extra():
    signature = ["field"]
    data = {"field": "value", "extra": "extra"}

    assert ["value"] == to_list(signature, data)

def test_to_list_multiple_fields_missing_data():
    signature = ["field1", "field2"]
    data = {"field1": "value"}

    with pytest.raises(KeyError):
        to_list(signature, data)

def test_to_list_multiple_fields_wrong_data():
    signature = ["field1", "field2"]
    data = {"wrong_field1": "value", "wrong_field2": "value"}

    with pytest.raises(KeyError):
        to_list(signature, data)

def test_to_list_multiple_fields_exact():
    signature = ["field1", "field2"]
    data = {"field1": "value1", "field2": "value2"}

    assert ["value1", "value2"] == to_list(signature, data)

def test_to_list_multiple_fields_extra():
    signature = ["field1", "field2"]
    data = {"field1": "value1", "extra": "extra", "field2": "value2"}

    assert ["value1", "value2"] == to_list(signature, data)

#===========================
#
# list --> dict conversion
#
#===========================

def test_to_dict_no_signature_exact():
    signature = []
    data = []

    assert {} == to_dict(signature, data)

def test_to_dict_no_signature_extra():
    signature = []
    data = ["extra"]

    to_dict(signature, data)

def test_to_dict_one_field_no_data():
    signature = ["field"]
    data = []

    with pytest.raises(ValueError):
        to_dict(signature, data)

def test_to_dict_one_field_exact():
    signature = ["field"]
    data = ["value"]

    assert {"field": "value"} == to_dict(signature, data)

def test_to_dict_one_field_extra():
    signature = ["field"]
    data = ["value", "extra"]

    with pytest.raises(ValueError):
        to_dict(signature, data)

def test_to_dict_multiple_fields_missing_data():
    signature = ["field1", "field2"]
    data = ["value"]

    with pytest.raises(ValueError):
        to_dict(signature, data)

def test_to_dict_multiple_fields_exact():
    signature = ["field1", "field2"]
    data = ["value1", "value2"]

    assert {"field1": "value1", "field2": "value2"} == to_dict(signature, data)

def test_to_dict_multiple_fields_extra():
    signature = ["field1", "field2"]
    data = ["value1", "value2", "value3"]

    with pytest.raises(ValueError):
        to_dict(signature, data)

#===========================
#
# Layers
#
#===========================

def test_layer_register():
    class Registry(object):
        registered = []
        def _register_layer(self, layer):
            Registry.registered.append(layer)
    registry = Registry()
    layer = Layer(registry)

    assert layer in registry.registered

def test_layer_calls_next():
    class Callable(object):
        called = False
        def handle_request(self, context):
            Callable.called = True

    next = Callable()
    context = {}

    layer = Layer()
    layer.handle_request(context, next)
    assert Callable.called

#===========================
#
# Stack
#
#===========================

def test_empty_stack():
    stack = Stack()
    stack.handle_request({})

def test_stack_executes_once():
    class CountLayer(object):
        count = 0
        def handle_request(self, context, next):
            CountLayer.count += 1

    layer = CountLayer()
    stack = Stack([layer])
    stack.handle_request({})
    stack.handle_request({})

    assert CountLayer.count == 1

def test_stack_execution_nesting():
    class Nested(object):
        order = []
        def handle_request(self, context, next):
            Nested.order.append(self)
            next.handle_request(context)
            Nested.order.append(self)

    layer1 = Nested()
    layer2 = Nested()
    layers = [layer1, layer2]

    stack = Stack(layers)
    stack.handle_request({})

    assert Nested.order == [layer1, layer2, layer2, layer1]

#===========================
#
# cached_property
#
#===========================

def test_cached_decorator():
    cls = cached_decorator_class()

    data = "Hello"
    # Class definition shouldn't increment
    assert 0 == cls.calls[data]

    # Instantiation shouldn't increment
    obj = cls()
    assert 0 == cls.calls[data]

    # First call increments
    assert data == obj.get(data)
    assert 1 == cls.calls[data]

    # Second call cached
    assert data == obj.get(data)
    assert 1 == cls.calls[data]

def test_cached_decorator_no_collisions():
    cls = cached_decorator_class()

    obj = cls()
    data = "Hello"
    other_data = "World"
    assert 0 == cls.calls[other_data]

    # First call increments - only data
    assert data == obj.get(data)
    assert 1 == cls.calls[data]
    assert 0 == cls.calls[other_data]

    # Second call cached - only data
    assert data == obj.get(data)
    assert 1 == cls.calls[data]
    assert 0 == cls.calls[other_data]

    # Cache other_data
    assert other_data == obj.get(other_data)

    # Different items cached
    assert 2 == len(cls.calls)

def test_cached_decorator_no_cache_on_throw():
    # This is probably an obvious case, but I always forget
    # how it works

    @cached
    def get():
        raise KeyError()

    # Doesn't cache since Exception occurs before assignemnt
    with pytest.raises(KeyError):
        get()

    # Still not cached
    with pytest.raises(KeyError):
        get()


#===========================
#
# cached_property
#
#===========================

def test_cached_property_get_invoked_once():
    cls = cached_property_class()

    # Class definition shouldn't invoke
    assert cls.gets == 0

    # Instantiation shouldn't invoke
    obj = cls()
    assert cls.gets == 0

    # First invocation, cache miss
    foo = obj.foo
    assert foo == "foo"
    assert cls.gets == 1

    # Second invocation, cache hit
    foo = obj.foo
    assert foo == "foo"
    assert cls.gets == 1

def test_cached_property_set():
    cls = cached_property_class()
    obj = cls()

    with pytest.raises(AttributeError):
        obj.foo = None
    assert cls.sets == 0

def test_cached_property_del():
    cls = cached_property_class()
    obj = cls()

    with pytest.raises(AttributeError):
        del obj.foo
    assert cls.dels == 0

def test_cached_property_get_no_obj():
    cp = cached_property()
    assert cp == cp.__get__(None)

def test_cached_property_get_no_fget():
    cp = cached_property(None)
    with pytest.raises(AttributeError):
        cp.__get__(True)

def test_cached_property_is_fragile():
    class other_decorator(property):
        pass

    class Class(object):
        @cached_property
        @other_decorator
        def foo(self):
            return "foo"

    obj = Class()
    with pytest.raises(AttributeError):
        obj.foo

#===========================
#
# Client
#
#===========================

def test_client_empty_description():
    with pytest.raises(AttributeError):
        Client(None)

def test_client_minimum_valid_description():
    data = {"name": "client"}
    description = ServiceDescription(data)
    Client(description)

def test_client_exceptions():
    data = {"name": "client", "exceptions": ["Exception1", "Exception2"]}
    description = ServiceDescription(data)
    client = Client(description)

    def raise_ex1():
        raise client.exceptions.Exception1()

    with pytest.raises(client.exceptions.Exception1):
        raise_ex1()

    # Can raise un-listed exceptions
    with pytest.raises(Exception):
        raise client.exceptions.DynamicExceptionClass("arg1", "arg2")

def test_client_operations_created():
    ops = ["op_"+str(i) for i in range(100)]
    data = {"name": "client", "operations": ops}
    description = ServiceDescription(data)
    client = Client(description)

    validate = lambda op: callable(getattr(client, op))
    assert all(map(validate, ops))

def test_client_config_fallbacks():
    # Fall all the way through to default
    data = {"name": "client"}
    description = ServiceDescription(data)
    client = Client(description)
    assert "default" == client._attr("metakey", "default")

    # Fall through to description
    data = {"name": "client", "metakey": "description"}
    description = ServiceDescription(data)
    client = Client(description)
    assert "description" == client._attr("metakey", "default")

    # Fall through to config
    data = {"name": "client", "metakey": "description"}
    description = ServiceDescription(data)
    client = Client(description, metakey="config")
    assert "config" == client._attr("metakey", "default")

def test_client_default_uri_and_timeout():
    data = {"name": "client"}
    client = dumb_client(data)

    assert "http://localhost:8080/client/{operation}" == client._uri
    assert 5 == client._timeout

def test_client_call_unknown_operation():
    data = {"name": "client"}
    client = dumb_client(data)

    with pytest.raises(KeyError):
        client._call("UnknownOperation", 1, 2, 3)

def test_client_call_missing_args():
    data = {"name": "client", "operations": [{"name": "operation", "input": ["arg1", "arg2"]}]}
    client = dumb_client(data)

    with pytest.raises(ValueError):
        client._call("operation", "arg1")

def test_client_call_extra_args():
    data = {"name": "client", "operations": [{"name": "operation", "input": ["arg1", "arg2"]}]}
    client = dumb_client(data)

    with pytest.raises(ValueError):
        client._call("operation", "arg1", "arg2", "extra")

def test_client_call_raises_on_serializer_failure():
    data = {"name": "client", "operations": [{"name": "operation", "input": ["arg1", "arg2"]}]}
    client = dumb_client(data)

    # json.encoder throws TypeError: <type 'NameError'> is not JSON serializable
    with pytest.raises(TypeError):
        client._call("operation", "arg1", NameError)

def test_client_call_raises_on_deserializer_failure():
    data = {"name": "client", "operations": ["operation1"]}
    description = ServiceDescription(data)
    client = Client(description)

    def malformed_handler(*a, **kw):
        return '{"name": [,}'
    client._wire_handler = malformed_handler

    with pytest.raises(ValueError):
        client._call("operation1")

def test_client_call_raises_exception_from_wire():
    data = {"name": "client", "operations": ["operation1"]}
    description = ServiceDescription(data)
    client = Client(description)
    class RealException(Exception):
        pass
    exception_args = ["message", 1, 2, 3]
    client._wire_handler = dumb_wire_handler(exception=RealException(*exception_args))
    with pytest.raises(client.exceptions.RealException):
        client._call("operation1")

def test_client_call_wire_missing_result():
    data = {"name": "client", "operations": [{"name": "operation", "output": ["result1", "result2"]}]}
    description = ServiceDescription(data)
    client = Client(description)

    output = {"result1": "wire_result"}
    client._wire_handler = dumb_wire_handler(output=output)

    with pytest.raises(client.exceptions.ServiceException):
        client._call("operation")

def test_client_call_wire_wrong_results():
    data = {"name": "client", "operations": [{"name": "operation", "output": ["result1", "result2"]}]}
    description = ServiceDescription(data)
    client = Client(description)

    output = {"result1": "wire_result", "wrong": "field"}
    client._wire_handler = dumb_wire_handler(output=output)

    with pytest.raises(client.exceptions.ServiceException):
        client._call("operation")

def test_client_call_returns_none():
    data = {"name": "client", "operations": ["operation"]}
    description = ServiceDescription(data)
    client = Client(description)

    # Doesn't matter if we return extra fields
    output = {"unused":"field"}
    client._wire_handler = dumb_wire_handler(output=output)

    result = client._call("operation")
    assert None is result

def test_client_call_single_return_value():
    data = {"name": "client", "operations": [{"name": "operation", "output": ["field"]}]}
    description = ServiceDescription(data)
    client = Client(description)

    # Doesn't matter if we return extra fields
    output = {"field":"value", "unused": "unused"}
    client._wire_handler = dumb_wire_handler(output=output)

    result = client._call("operation")
    assert "value" == result

def test_client_call_none_is_valid_single_return():
    data = {"name": "client", "operations": [{"name": "operation", "output": ["field"]}]}
    description = ServiceDescription(data)
    client = Client(description)

    # Doesn't matter if we return extra fields
    output = {"field": None, "unused": "unused"}
    client._wire_handler = dumb_wire_handler(output=output)

    result = client._call("operation")
    assert None is result

def test_client_call_multiple_return_values():
    data = {"name": "client", "operations": [{"name": "operation", "output": ["field1", "field2"]}]}
    description = ServiceDescription(data)
    client = Client(description)

    output = {"field1": "value1", "field2": "value2"}
    client._wire_handler = dumb_wire_handler(output=output)

    result1, result2 = client._call("operation")
    assert "value1" == result1
    assert "value2" == result2

def test_client_operation_building():
    data = {"name": "client", "operations": [{"name": "my_operation", "input": ["arg1", "arg2"]}]}
    client = dumb_client(data)

    assert callable(client.my_operation)
    with pytest.raises(AttributeError):
        assert not callable(client.unknown_operation)

def test_client_wire_handler_exception_wrapping():
    data = {"name": "client", "operations": [{"name": "my_operation", "input": ["arg1", "arg2"]}]}
    description = ServiceDescription(data)
    client = Client(description)

    def handler(*a, **kw):
        raise Exception("wire handler raised")
    client._wire_handler = handler

    with pytest.raises(client.exceptions.ServiceException):
        client._call("my_operation", 1, 2)


def test_client_handle_exception_raises():
    '''
    def _handle_exception(self, context):
        if "__exception" in context and len(context) == 1:
            exception = context["__exception"]
            ex_cls = getattr(self.exceptions, exception["cls"])
            raise ex_cls(*exception["args"])
    '''
    data = {"name": "client"}
    description = ServiceDescription(data)
    client = Client(description)

    context = {
        "__exception" : {
            "cls": "MyException",
            "args": [1, 2, "Hello"]
        }
    }

    with pytest.raises(client.exceptions.MyException):
        client._handle_exception(context)

def test_client_handle_exception_no_raise():
    data = {"name": "client"}
    description = ServiceDescription(data)
    client = Client(description)


    # Shouldn't raise, because __exception object isn't sole context object
    context = {
        "__exception" : {
            "cls": "MyException",
            "args": [1, 2, "Hello"]
        },
        "other_field": "value"
    }
    client._handle_exception(context)

    # Shouldn't raise, key isn't __exception
    context = {
        "not_exception" : {
            "cls": "MyException",
            "args": [1, 2, "Hello"]
        }
    }
    client._handle_exception(context)

#===========================
#
# Service
#
#===========================

def test_service_empty_description():
    with pytest.raises(AttributeError):
        Service(None)

def test_service_minimum_valid_description():
    data = {"name": "service"}
    description = ServiceDescription(data)
    Service(description)

def test_service_config_fallbacks():
    # Fall all the way through to default
    data = {"name": "service"}
    description = ServiceDescription(data)
    service = Service(description)
    assert "default" == service._attr("metakey", "default")

    # Fall through to description
    data = {"name": "service", "metakey": "description"}
    description = ServiceDescription(data)
    service = Service(description)
    assert "description" == service._attr("metakey", "default")

    # Fall through to init config
    data = {"name": "service", "metakey": "description"}
    description = ServiceDescription(data)
    service = Service(description, metakey="init_config")
    assert "init_config" == service._attr("metakey", "default")

    # Fall through to run config
    data = {"name": "service", "metakey": "description"}
    description = ServiceDescription(data)
    service = Service(description, metakey="init_config")
    service._run_config["metakey"] = "run_config"
    assert "run_config" == service._attr("metakey", "default")

def test_service_run_preserves_kwargs():
    data = {"name": "service"}
    description = ServiceDescription(data)
    service = Service(description)
    service._app = Container()

    run_args = [1, False, type]
    run_kwargs = {
        "some": "field",
        "other": [ "string", 1, None, {} ]
    }
    def run(*a, **kw):
        assert run_args == list(a)
        assert run_kwargs == kw
    service._app.run = run

    service.run(*run_args, **run_kwargs)
    assert "field" == service._attr("some", None)

def test_service_bottle_call_unknown_operation():
    data = {"name": "service"}
    description = ServiceDescription(data)
    service = Service(description)

    with pytest.raises(bottle.HTTPError):
        service._bottle_call("UnknownOperation")

def test_service_bottle_call_raises_when_call_raises():
    data = {"name": "service", "operations": ["operation"]}
    description = ServiceDescription(data)
    service = Service(description)

    def mock_call(operation, body):
        raise ValueError("service._call raised")
    service._call = mock_call
    service._bottle = mock_bottle()

    with pytest.raises(bottle.HTTPError):
        service._bottle_call("operation")

def test_service_bottle_call_passes_operation_correctly():
    data = {"name": "service", "operations": ["operation"]}
    description = ServiceDescription(data)
    service = Service(description)

    expected_operation = "operation"
    expected_body = "hello, this is body"
    expected_return = "no, this is patrick"

    def mock_call(operation, body):
        assert expected_operation == operation
        assert expected_body == body
        return expected_return
    service._call = mock_call
    service._bottle = mock_bottle(expected_body)

    assert expected_return == service._bottle_call("operation")

def test_service_handle_whitelisted_exception():
    data = {"name": "service", "exceptions": ["MyException"]}
    description = ServiceDescription(data)
    service = Service(description)
    class MyException(Exception):
        pass
    exception = MyException()
    data = service._handle_exception(exception)
    assert 1 == len(data)
    assert "MyException" == data["__exception"]["cls"]
    assert not data["__exception"]["args"]

def test_service_handle_non_whitelisted_exception():
    data = {"name": "service"}
    description = ServiceDescription(data)
    service = Service(description)
    class MyException(Exception):
        pass
    exception = MyException()
    data = service._handle_exception(exception)
    assert 1 == len(data)
    assert "ServiceException" == data["__exception"]["cls"]
    assert ["Internal Error"] == data["__exception"]["args"]

def test_service_handle_non_whitelisted_exception_while_debugging():
    data = {"name": "service"}
    description = ServiceDescription(data)
    service = Service(description, debug=True)
    class MyException(Exception):
        pass
    exception = MyException(1,2, 3)
    data = service._handle_exception(exception)
    assert 1 == len(data)
    assert "MyException" == data["__exception"]["cls"]
    assert (1, 2, 3) == data["__exception"]["args"]

def test_service_operation_decorator_unknown_operation():
    data = {"name": "service"}
    description = ServiceDescription(data)
    service = Service(description)

    with pytest.raises(ValueError):
        service.operation("UnknownOperation")

def test_service_operation_decorator_infer_operation_name():
    data = {"name": "service", "operations":["operation_name"]}
    description = ServiceDescription(data)
    service = Service(description)
    service._wrap_func = dumb_func_wrapper()

    def operation_name():
        pass

    assert operation_name is service.operation(operation_name)

def test_service_operation_decorator_returns_decorator():
    data = {"name": "service", "operations":["operation_name"]}
    description = ServiceDescription(data)
    service = Service(description)
    service._wrap_func = dumb_func_wrapper()

    def operation_name():
        pass

    decorator = service.operation("operation_name")
    assert callable(decorator)
    assert operation_name is decorator(operation_name)

def test_service_wrap_func_with_vargs():
    data = {"name": "service", "operations":[{"name": "operation_name", "input": ["arg1", "arg2"]}]}
    description = ServiceDescription(data)
    service = Service(description)

    with pytest.raises(ValueError):
        def vargs_func(arg1, *args): pass
        service._wrap_func("operation_name", vargs_func)

    with pytest.raises(ValueError):
        def vargs_func(arg1, arg2, *args): pass
        service._wrap_func("operation_name", vargs_func)

def test_service_wrap_func_with_kwargs():
    data = {"name": "service", "operations":[{"name": "operation_name", "input": ["arg1", "arg2"]}]}
    description = ServiceDescription(data)
    service = Service(description)

    with pytest.raises(ValueError):
        def vargs_func(arg1, **kwargs): pass
        service._wrap_func("operation_name", vargs_func)

    with pytest.raises(ValueError):
        def vargs_func(arg1, arg2, **kwargs): pass
        service._wrap_func("operation_name", vargs_func)

def test_service_wrap_func_bad_sig_missing_args():
    data = {"name": "service", "operations":[{"name": "operation_name", "input": ["arg1", "arg2"]}]}
    description = ServiceDescription(data)
    service = Service(description)

    def func(arg1): pass
    with pytest.raises(ValueError):
        service._wrap_func("operation_name", func)

def test_service_wrap_func_bad_sig_extra_args():
    data = {"name": "service", "operations":[{"name": "operation_name", "input": ["arg1", "arg2"]}]}
    description = ServiceDescription(data)
    service = Service(description)

    def func(arg1, arg2, arg3): pass
    with pytest.raises(ValueError):
        service._wrap_func("operation_name", func)

def test_service_wrap_func_bad_wrong_args():
    data = {"name": "service", "operations":[{"name": "operation_name", "input": ["arg1", "arg2"]}]}
    description = ServiceDescription(data)
    service = Service(description)

    def func(arg_names, are_wrong): pass
    with pytest.raises(ValueError):
        service._wrap_func("operation_name", func)

def test_service_wrap_func_bad_sig_args_wrong_order():
    data = {"name": "service", "operations":[{"name": "operation_name", "input": ["arg1", "arg2"]}]}
    description = ServiceDescription(data)
    service = Service(description)

    def func(arg2, arg1): pass
    with pytest.raises(ValueError):
        service._wrap_func("operation_name", func)

def test_service_wrap_func_returns_original():
    data = {"name": "service", "operations":[{"name": "operation_name", "input": ["arg1", "arg2"]}]}
    description = ServiceDescription(data)
    service = Service(description)

    def func(arg1, arg2): pass
    assert func is service._wrap_func("operation_name", func)

def test_service_call_missing_args():
    data = {"name": "service", "operations":[{
        "name": "operation_name",
        "input": ["arg1", "arg2", "arg3"],
        "output": ["result1", "result2"]
    }]}
    description = ServiceDescription(data)
    service = Service(description)

    @service.operation("operation_name")
    def func(arg1, arg2, arg3):
        return "value1", "value2"

    operation = "operation_name"
    body = json.dumps({"arg1": "input1", "arg2": "input2"})

    output = service._call(operation, body)
    assert is_exception(output, "ServiceException")

def test_service_call_wrong_args():
    data = {"name": "service", "operations":[{
        "name": "operation_name",
        "input": ["arg1", "arg2", "arg3"],
        "output": ["result1", "result2"]
    }]}
    description = ServiceDescription(data)
    service = Service(description)

    @service.operation("operation_name")
    def func(arg1, arg2, arg3):
        return "value1", "value2"

    operation = "operation_name"
    body = json.dumps({"arg1": "input1", "arg2": "input2", "wrong": "argname"})

    output = service._call(operation, body)
    assert is_exception(output, "ServiceException")

def test_service_call_raises_whitelisted_exception_on_func_raise():
    data = {"name": "service",
        "operations":[{
            "name": "operation_name",
            "input": ["arg1", "arg2", "arg3"],
            "output": ["result1", "result2"]
        }],
        "exceptions": ["MyException"]
    }
    description = ServiceDescription(data)
    service = Service(description)

    @service.operation("operation_name")
    def func(arg1, arg2, arg3):
        raise MyException(1, 2, 3)

    class MyException(Exception): pass

    operation = "operation_name"
    body = json.dumps({"arg1": "input1", "arg2": "input2", "arg3": "input3"})

    output = service._call(operation, body)
    assert is_exception(output, "MyException")

def test_service_call_raises_service_exception_on_func_raise():
    data = {"name": "service",
        "operations":[{
            "name": "operation_name",
            "input": ["arg1", "arg2", "arg3"],
            "output": ["result1", "result2"]
        }]
    }
    description = ServiceDescription(data)
    service = Service(description)

    @service.operation("operation_name")
    def func(arg1, arg2, arg3):
        raise MyException(1, 2, 3)

    class MyException(Exception): pass

    operation = "operation_name"
    body = json.dumps({"arg1": "input1", "arg2": "input2", "arg3": "input3"})

    output = service._call(operation, body)
    assert is_exception(output, "ServiceException")

def test_service_call_returns_serialized_output():
    data = {"name": "service",
        "operations":[{
            "name": "operation_name",
            "input": ["arg1", "arg2", "arg3"],
            "output": ["result1", "result2"]
        }]
    }
    description = ServiceDescription(data)
    service = Service(description)

    @service.operation("operation_name")
    def func(arg1, arg2, arg3):
        return "value1", "value2"

    operation = "operation_name"
    body = json.dumps({"arg1": "input1", "arg2": "input2", "arg3": "input3"})

    output = service._call(operation, body)
    expected_output = {"result1": "value1", "result2": "value2"}
    assert expected_output == json.loads(output)

def test_service_call_returns_serialized_output_single_value():
    data = {"name": "service",
        "operations":[{
            "name": "operation_name",
            "input": ["arg1", "arg2", "arg3"],
            "output": ["result1"]
        }]
    }
    description = ServiceDescription(data)
    service = Service(description)

    @service.operation("operation_name")
    def func(arg1, arg2, arg3):
        return "value1"

    operation = "operation_name"
    body = json.dumps({"arg1": "input1", "arg2": "input2", "arg3": "input3"})

    output = service._call(operation, body)
    expected_output = {"result1": "value1"}
    assert expected_output == json.loads(output)

def test_service_call_returns_serialized_output_no_value():
    data = {"name": "service",
        "operations":[{
            "name": "operation_name",
            "input": ["arg1", "arg2", "arg3"]
        }]
    }
    description = ServiceDescription(data)
    service = Service(description)

    @service.operation("operation_name")
    def func(arg1, arg2, arg3):
        pass

    operation = "operation_name"
    body = json.dumps({"arg1": "input1", "arg2": "input2", "arg3": "input3"})

    output = service._call(operation, body)
    expected_output = {}
    assert expected_output == json.loads(output)

def test_server_call_raises_on_deserialize_failure():
    data = {"name": "service",
        "operations":[{
            "name": "operation_name",
            "input": ["arg1", "arg2", "arg3"],
            "output": ["result1", "result2"]
        }]
    }
    description = ServiceDescription(data)
    service = Service(description)

    @service.operation("operation_name")
    def func(arg1, arg2, arg3):
        return "value1", "value2"

    operation = "operation_name"
    body = '{"name": [],}}'

    with pytest.raises(ValueError):
        service._call(operation, body)

def test_server_call_raises_on_serialize_failure():
    data = {"name": "service",
        "operations":[{
            "name": "operation_name",
            "input": ["arg1", "arg2", "arg3"],
            "output": ["result1", "result2"]
        }]
    }
    description = ServiceDescription(data)
    service = Service(description)

    @service.operation("operation_name")
    def func(arg1, arg2, arg3):
        return "value1", NameError

    operation = "operation_name"
    body = json.dumps({"arg1": "input1", "arg2": "input2", "arg3": "input3"})

    # json.encoder throws TypeError: <type 'NameError'> is not JSON serializable
    with pytest.raises(TypeError):
        service._call(operation, body)

#===========================
#
# End-to-end tests
#
#===========================

def test_e2e_no_return():
    data = {"name": "service",
        "operations":[{
            "name": "signal",
            "input": ["arg1"],
        }]
    }
    description = ServiceDescription(data)
    client = Client(description)
    service = Service(description)
    connect(client, service)

    called = [False]
    @service.operation
    def signal(arg1):
        called[0] = True

    assert None == client.signal("foo")
    assert called[0]

def test_e2e_single_return():
    data = {"name": "service",
        "operations":[{
            "name": "echo",
            "input": ["arg1"],
            "output": ["out1"]
        }]
    }
    description = ServiceDescription(data)
    client = Client(description)
    service = Service(description)
    connect(client, service)

    called = [False]
    @service.operation
    def echo(arg1):
        called[0] = True
        return arg1

    for value in ["foo", None, False, -1]:
        called[0] = False
        assert value == client.echo(value)
        assert called[0]

#===========================
#
# Helpers for testing
#
#===========================

@contextmanager
def removed_global(name):
    builtins = six.moves.builtins

    # Save object so we can put it back after the test
    obj = getattr(builtins, name)
    delattr(builtins, name)

    yield

    # Put the object back so other tests don't break
    setattr(builtins, name, obj)

def cached_property_class():
    class Class(object):
        gets = 0
        sets = 0
        dels = 0

        @cached_property
        def foo(self):
            Class.gets += 1
            return "foo"

        @foo.setter
        def foo(self, value):
            Class.sets += 1

        @foo.deleter
        def foo(self):
            Class.dels += 1
    return Class

def cached_decorator_class():
    class Class(object):
        calls = defaultdict(int)

        @cached
        def get(self, data):
            Class.calls[data] += 1
            return data
    return Class

def valid_description_string():
    return """
    {
        "name": "service",
        "operations": [
            {
                "name": "operation1",
                "input": ["arg1", "arg2"],
                "output": []
            },
            {
                "name": "operation2",
                "input": ["arg1"],
                "output": ["value1"]
            },
            {
                "name": "operation3",
                "input": [],
                "output": ["value1", "value2"]
            }
        ],
        "exceptions": ["exception1", "exception2"]
    }
    """

def dumb_wire_handler(output=None, exception=None):
    '''Construct a dumb wire handler that returns a fixed json'''
    if exception:
        result = json.dumps({
            "__exception": {
                "cls": exception.__class__.__name__,
                "args": exception.args
            }
        })
    else:
        result = json.dumps(output)

    def handler(*args, **kwargs):
        return result
    return handler

def dumb_client(data):
    '''
    Dumb client with an empty wire handler

    Useful for testing exceptions that should occur
    before the wire handler is invoked
    '''
    description = ServiceDescription(data)
    client = Client(description)
    def noop(*a, **kw):
        raise BaseException("Handler called")
    client._wire_handler = noop
    return client

def mock_bottle(string=""):
    '''Sets (mocked)bottle.request.body = IOBytes of string'''
    mock_bottle = Container()
    mock_bottle.abort = bottle.abort
    mock_bottle.request = Container()
    mock_bottle.request.body = six.BytesIO(six.b(string))
    return mock_bottle

def dumb_func_wrapper():
    def wrap(operation, func, **kwargs):
        return func
    return wrap

class Container(object): pass

def is_exception(string, exception_cls):
    data = json.loads(string)
    return exception_cls == data["__exception"]["cls"]

def connect(client, service):
    '''
    Hook service._call up directly as the client's wire_handler
    Only works when client sends a well-formed uri to the wire handler.

    This allows testing pyservice end-to-end without requests/bottle dependencies
    '''
    URI_RE = re.compile(client._uri.replace('{operation}', '(.*)'))
    def wire_handler(uri, data='', **kwargs):
        operation = URI_RE.match(uri).groups()[0]
        return service._call(operation, data)
    client._wire_handler = wire_handler
