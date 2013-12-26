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
from pyservice.extension import extension, execute, Extension
from pyservice.serialize import JsonSerializer, to_list, to_dict
from pyservice.util import cached, cached_property
from pyservice.client import Client, WebServiceClient
from pyservice.service import WebService
from pyservice.handlers import ClientHandler

# Common description for testing Client, Service
basic_description_string = """{
    "name": "service",
    "operations": [
        "void",
        {
            "name": "signal",
            "input": ["exec_id"]
        },
        {
            "name": "echo",
            "input": ["value"],
            "output": ["value"]
        },
        {
            "name": "multiecho",
            "input": ["value1", "value2"],
            "output": ["value1", "value2"]
        }
    ],
    "exceptions": [
        "WhitelistedException",
        "AnotherWhitelistedException"
    ]
}"""

basic_description = ServiceDescription.from_string(basic_description_string)

def basic_client(**config):
    return WebServiceClient(basic_description, **config)

def basic_service(**config):
    return WebService(basic_description, **config)

#===========================
#
# Description helpers:
#     validate_name,
#     parse_metadata
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
    data = json.loads(basic_description_string.replace('\n', ''))
    desc = Description.from_json(data)
    assert "service" == desc.name
    assert data is not desc._obj

def test_description_from_string():
    Description.from_string(basic_description_string)

def test_description_from_file():
    with tempfile.NamedTemporaryFile(mode='w+') as file_obj:
        file_obj.write(basic_description_string)
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
    service = ServiceDescription.from_string(basic_description_string)

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
# @extension
#
#===========================

def test_extension_decorator_empty_handler():
    def next_handler(context):
        context["next_called"] = True

    @extension
    def empty_handler(context):
        pass
    context = {"next_called": False}
    empty_handler().handle_operation(context, next_handler)
    assert not context["next_called"]

def test_extension_decorator_noop_handler():
    def next_handler(context):
        context["next_called"] = True

    @extension
    def empty_handler(context):
        yield
    context = {"next_called": False}
    empty_handler().handle_operation(context, next_handler)
    assert context["next_called"]

def test_extension_decorator_yield_ordering():
    def next_handler(context):
        context["order"].append("Chain")

    @extension
    def ordering_handler(context):
        context["order"].append("Before")
        yield
        context["order"].append("After")

    context = {"order": []}
    ordering_handler().handle_operation(context, next_handler)
    assert ["Before", "Chain", "After"] == context["order"]

def test_extension_decorator_no_after():
    def next_handler(context):
        context["order"].append("Chain")

    @extension
    def ordering_handler(context):
        context["order"].append("Before")
        yield

    context = {"order": []}
    ordering_handler().handle_operation(context, next_handler)
    assert ["Before", "Chain"] == context["order"]

def test_extension_decorator_invalid_multiple_yields():
    next_handler = lambda context: None

    @extension
    def bad_handler(context):
        yield
        yield
    context = {}

    with pytest.raises(RuntimeError):
        bad_handler().handle_operation(context, next_handler)

def test_extension_decorator_next_raises():
    def next_handler(context):
        context["order"].append("Chain")
        raise ValueError()

    @extension
    def bad_handler(context):
        context["order"].append("Before")
        yield
    context = {"order": []}

    with pytest.raises(ValueError):
        bad_handler().handle_operation(context, next_handler)
    assert ["Before", "Chain"] == context["order"]

def test_extension_decorator_catches():
    def next_handler(context):
        context["order"].append("Chain")
        raise BaseException()

    @extension
    def bad_handler(context):
        try:
            context["order"].append("Before")
            yield
        finally:
            context["order"].append("After")
    context = {"order": []}

    try:
        bad_handler().handle_operation(context, next_handler)
    except BaseException:
        pass

    assert ["Before", "Chain", "After"] == context["order"]

def test_extension_decorator_explicit_StopIteration():

    next_handler = lambda context: None

    @extension
    def noop_handler(context):
        # Returns a generator that immediately raises StopIteration
        return (x for x in [])
    context = {}

    noop_handler().handle_operation(context, next_handler)

#===========================
#
# execute / ExtensionExecutor
#
#===========================

def test_ExtensionExecutor_empty_handlers():
    context = {}
    execute([], "handle_operation", context)

def test_ExtensionExecutor_single_handler():
    @extension
    def some_extension(context):
        context["calls"] += 1
    context = {"calls": 0}
    execute([some_extension()], "handle_operation", context)
    assert 1 == context["calls"]

    # Multiple calls
    execute([some_extension()], "handle_operation", context)
    assert 2 == context["calls"]

def test_ExtensionExecutor_second_handler_not_invoked():
    @extension
    def first_extension(context):
        context["order"].append("first")

    @extension
    def second_extension(context):
        context["order"].append("second_before")
        yield
        context["order"].append("second_after")

    context = {"order": []}
    handlers = [first_extension(), second_extension()]
    execute(handlers, "handle_operation", context)
    assert ["first"] == context["order"]

def test_ExtensionExecutor_handler_ordering():
    @extension
    def first_extension(context):
        context["order"].append("first_before")
        yield
        context["order"].append("first_after")

    @extension
    def second_extension(context):
        context["order"].append("second_before")
        yield
        context["order"].append("second_after")


    context = {"order": []}
    handlers = [first_extension(), second_extension()]
    execute(handlers, "handle_operation", context)
    expected_order = ["first_before", "second_before", "second_after", "first_after"]
    assert expected_order == context["order"]

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
        WebServiceClient(None)

def test_client_minimum_valid_description():
    data = {"name": "client"}
    description = ServiceDescription(data)
    WebServiceClient(description)

def test_client_exceptions():
    client = basic_client()

    def raise_ex():
        raise client.exceptions.WhitelistedException()

    with pytest.raises(client.exceptions.WhitelistedException):
        raise_ex()

    # Can raise un-listed exceptions
    with pytest.raises(Exception):
        raise client.exceptions.DynamicExceptionClass("arg1", "arg2")

def test_client_operations_created():
    operations = ["void", "signal", "echo", "multiecho"]
    client = basic_client()

    validate = lambda op: callable(getattr(client, op))
    assert all(map(validate, operations))

def test_client_config_fallbacks():
    # Fall all the way through to default
    data = {"name": "client"}
    description = ServiceDescription(data)
    client = WebServiceClient(description)
    assert "default" == client.config.get("metakey", "default")

    # Fall through to description
    data = {"name": "client", "metakey": "description"}
    description = ServiceDescription(data)
    client = WebServiceClient(description)
    assert "description" == client.config.get("metakey", "default")

    # Fall through to config
    data = {"name": "client", "metakey": "description"}
    description = ServiceDescription(data)
    client = WebServiceClient(description, metakey="config")
    assert "config" == client.config.get("metakey", "default")

def test_client_config_falsey_values():
    data = {"name": "client", "metakey": True}
    description = ServiceDescription(data)
    client = WebServiceClient(description, metakey=False)

    # Should get false, since init config overrides description metadata
    assert False is client.config.get("metakey", None)

def test_client_call_unknown_operation():
    client = basic_client()
    with pytest.raises(KeyError):
        client._call("UnknownOperation", 1, 2, 3)

def test_client_call_missing_args():
    client = basic_client()
    with pytest.raises(ValueError):
        client._call("multiecho", "only one value")

def test_client_call_extra_args():
    client = basic_client()
    with pytest.raises(ValueError):
        client._call("echo", "extra", "arg")

def test_client_call_raises_on_serializer_failure():
    client = basic_client()

    # json.encoder throws TypeError: <type 'NameError'> is not JSON serializable
    with pytest.raises(TypeError):
        client._call("echo", NameError)

def test_client_call_raises_on_deserializer_failure():
    client = basic_client()
    client.handler = MalformedClientHandler()

    with pytest.raises(ValueError):
        client._call("void")

def test_client_call_raises_exception_from_wire():
    client = basic_client()
    class RealException(Exception):
        pass
    exception_args = ["message", 1, 2, 3]
    client.handler = dumb_wire_handler(exception=RealException(*exception_args))
    with pytest.raises(client.exceptions.RealException):
        client._call("void")

def test_client_call_wire_missing_result():
    client = basic_client()

    output = {"value1": "some value"}
    client.handler = dumb_wire_handler(output=output)

    with pytest.raises(client.exceptions.ServiceException):
        client._call("multiecho", "some value", "missing")

def test_client_call_wire_wrong_results():
    client = basic_client()

    output = {"value1": "some value", "wrong": "field"}
    client.handler = dumb_wire_handler(output=output)

    with pytest.raises(client.exceptions.ServiceException):
        client._call("multiecho", "some value", "other")

def test_client_call_returns_none():
    client = basic_client()

    # Doesn't matter if we return extra fields
    output = {"unused":"field"}
    client.handler = dumb_wire_handler(output=output)

    result = client._call("void")
    assert None is result

def test_client_call_single_return_value():
    client = basic_client()

    # Doesn't matter if we return extra fields
    output = {"value": "some value", "unused": "unused"}
    client.handler = dumb_wire_handler(output=output)

    result = client._call("echo", "some value")
    assert "some value" == result

def test_client_call_none_is_valid_single_return():
    client = basic_client()

    # Doesn't matter if we return extra fields
    output = {"value": None, "unused": "unused"}
    client.handler = dumb_wire_handler(output=output)

    result = client._call("echo", None)
    assert None is result

def test_client_call_multiple_return_values():
    client = basic_client()

    output = {"value1": "value1", "value2": "value2"}
    client.handler = dumb_wire_handler(output=output)

    result1, result2 = client._call("multiecho", "value1", "value2")
    assert "value1" == result1
    assert "value2" == result2

def test_client_operation_building():
    client = basic_client()

    assert callable(client.void)
    with pytest.raises(AttributeError):
        assert not callable(client.unknown_operation)

def test_client_wire_handler_exception_wrapping():
    client = basic_client()
    client.handler = RaiseClientHandler()

    with pytest.raises(client.exceptions.ServiceException):
        client._call("void")


def test_client_handle_exception_raises():
    client = basic_client()
    context = {
        "__exception" : {
            "cls": "MyException",
            "args": [1, 2, "Hello"]
        }
    }

    with pytest.raises(client.exceptions.MyException):
        client._handle_exception(context)

def test_client_handle_exception_no_raise():
    client = basic_client()

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

def test_client_handler_invoked():
    client = basic_client()
    value1, value2 = "Hello", "World"
    values = {"value1": value1, "value2": value2}
    client.handler = dumb_wire_handler(output=values)

    @extension
    def capture(context):
        captured_context["input"] = dict(context["input"])
        yield
        captured_context["output"] = dict(context["output"])
    captured_context = {}
    client.add_extension(capture())

    result1, result2 = client.multiecho(value1, value2)

    # Handler doesn't mess with return unpacking
    assert (result1, result2) == (value1, value2)

    # Handler captures input/output
    assert values == captured_context["input"]
    assert values == captured_context["output"]

#===========================
#
# Service
#
#===========================

def test_service_empty_description():
    with pytest.raises(AttributeError):
        WebService(None)

def test_service_minimum_valid_description():
    data = {"name": "service"}
    description = ServiceDescription(data)
    WebService(description)

def test_service_config_fallbacks():
    # Fall all the way through to default
    data = {"name": "service"}
    description = ServiceDescription(data)
    service = WebService(description)
    assert "default" == service.config.get("metakey", "default")

    # Fall through to description
    data = {"name": "service", "metakey": "description"}
    description = ServiceDescription(data)
    service = WebService(description)
    assert "description" == service.config.get("metakey", "default")

    # Fall through to init config
    data = {"name": "service", "metakey": "description"}
    description = ServiceDescription(data)
    service = WebService(description, metakey="init_config")
    assert "init_config" == service.config.get("metakey", "default")

def test_service_config_falsey_values():
    data = {"name": "service", "metakey": True}
    description = ServiceDescription(data)
    service = WebService(description, metakey=False)

    # Should get false, since init config overrides description metadata
    assert False is service.config.get("metakey", None)

def test_service_run_preserves_kwargs():
    data = {"name": "service"}
    description = ServiceDescription(data)
    service = WebService(description)
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
    assert "field" == service.config.get("some", None)

def test_service_bottle_call_unknown_operation():
    service = basic_service()

    with pytest.raises(bottle.HTTPError):
        service._bottle_call("UnknownOperation")

def test_service_bottle_call_raises_when_call_raises():
    service = basic_service()

    def mock_call(operation, body):
        raise ValueError("service._call raised")
    service._call = mock_call

    with pytest.raises(bottle.HTTPError):
        service._bottle_call("void")

def test_service_bottle_call_passes_operation_correctly():
    service = basic_service()

    expected_operation = "void"
    expected_body = "hello, this is body"
    expected_return = "no, this is patrick"

    def mock_call(operation, body):
        assert expected_operation == operation
        assert expected_body == body
        return expected_return
    service._call = mock_call
    service._bottle = mock_bottle(expected_body)

    assert expected_return == service._bottle_call("void")

def test_service_handle_whitelisted_exception():
    service = basic_service()
    class WhitelistedException(Exception):
        pass
    exception = WhitelistedException()
    data = service._handle_exception(exception)
    assert 1 == len(data)
    assert "WhitelistedException" == data["__exception"]["cls"]
    assert not data["__exception"]["args"]

def test_service_handle_non_whitelisted_exception():
    service = basic_service()
    class NotWhitelistedException(Exception):
        pass
    exception = NotWhitelistedException()
    data = service._handle_exception(exception)
    assert 1 == len(data)
    assert "ServiceException" == data["__exception"]["cls"]
    assert ["Internal Error"] == data["__exception"]["args"]

def test_service_handle_non_whitelisted_exception_while_debugging():
    service = basic_service(debug=True)
    class NotWhitelistedException(Exception):
        pass
    exception = NotWhitelistedException(1,2, 3)
    data = service._handle_exception(exception)
    assert 1 == len(data)
    assert "NotWhitelistedException" == data["__exception"]["cls"]
    assert (1, 2, 3) == data["__exception"]["args"]

def test_service_operation_decorator_unknown_operation():
    service = basic_service()
    with pytest.raises(ValueError):
        service.operation("UnknownOperation")

def test_service_operation_decorator_returns_decorator():
    service = basic_service()

    def void(): pass
    decorator = service.operation("void")
    assert callable(decorator)
    assert void is decorator(void)

def test_service_wrap_func_with_vargs():
    service = basic_service()

    with pytest.raises(ValueError):
        @service.operation("echo")
        def vargs_func(arg1, *args): pass

    with pytest.raises(ValueError):
        @service.operation("multiecho")
        def vargs_func(arg1, arg2, *args): pass

def test_service_wrap_func_with_kwargs():
    service = basic_service()

    with pytest.raises(ValueError):
        @service.operation("echo")
        def vargs_func(arg1, **kwargs): pass

    with pytest.raises(ValueError):
        @service.operation("multiecho")
        def vargs_func(arg1, arg2, **kwargs): pass

def test_service_wrap_func_properly_inspect_closure():
    # Added because the previous method of comparing
    #   func.__code__.co_varnames
    #   func.__code__.co_argcount
    # is flawed - co_varnames includes
    # variable names within the function
    service = basic_service()

    @service.operation("echo")
    def echo(value):
        hello = 'World'
        pass

def test_service_wrap_func_bad_sig_missing_args():
    service = basic_service()

    def func(): pass
    with pytest.raises(ValueError):
        @service.operation("echo")
        def func(): pass

def test_service_wrap_func_bad_sig_extra_args():
    service = basic_service()

    def func(extra_arg1): pass
    with pytest.raises(ValueError):
        @service.operation("void")
        def func(extra_arg1): pass

def test_service_wrap_func_bad_wrong_args():
    service = basic_service()

    with pytest.raises(ValueError):
        @service.operation("multiecho")
        def func(arg_names, are_wrong): pass

def test_service_wrap_func_bad_sig_args_wrong_order():
    service = basic_service()

    with pytest.raises(ValueError):
        @service.operation("multiecho")
        def func(value2, value1): pass

def test_service_wrap_func_returns_original():
    service = basic_service()

    def func(value): pass
    assert func is service.operation("echo")(func)

def test_service_call_missing_args():
    service = basic_service()

    @service.operation("multiecho")
    def func(value1, value2):
        return value1, value2

    operation = "multiecho"
    body = json.dumps({"value1": "some value"})
    output = service._call(operation, body)
    assert is_exception(output, "ServiceException")

def test_service_call_wrong_args():
    service = basic_service()

    @service.operation("multiecho")
    def func(value1, value2):
        return value1, value2

    operation = "multiecho"
    body = json.dumps({"value1": "some value", "wrong": "argname"})
    output = service._call(operation, body)
    assert is_exception(output, "ServiceException")

def test_service_call_raises_whitelisted_exception_on_func_raise():
    service = basic_service()

    @service.operation("echo")
    def func(value):
        raise WhitelistedException
    class WhitelistedException(Exception): pass

    operation = "echo"
    body = json.dumps({"value": "some value"})
    output = service._call(operation, body)
    assert is_exception(output, "WhitelistedException")

def test_service_call_raises_service_exception_on_func_raise():
    service = basic_service()

    @service.operation("echo")
    def func(value):
        raise NotWhitelistedException(1, 2, 3)

    class NotWhitelistedException(Exception): pass

    operation = "echo"
    body = json.dumps({"value": "some value"})

    output = service._call(operation, body)
    assert is_exception(output, "ServiceException")

def test_service_call_returns_serialized_output():
    service = basic_service()

    @service.operation("multiecho")
    def func(value1, value2):
        return value1, value2

    operation = "multiecho"
    body = json.dumps({"value1": "some value", "value2": "other value"})

    output = service._call(operation, body)
    expected_output = {"value1": "some value", "value2": "other value"}
    assert expected_output == json.loads(output)

def test_service_call_returns_serialized_output_single_value():
    service = basic_service()

    @service.operation("echo")
    def func(value):
        return value

    operation = "echo"
    body = json.dumps({"value": "some value"})

    output = service._call(operation, body)
    expected_output = {"value": "some value"}
    assert expected_output == json.loads(output)

def test_service_call_returns_serialized_output_no_value():
    service = basic_service()

    @service.operation("signal")
    def func(exec_id):
        return None

    operation = "signal"
    body = json.dumps({"exec_id": "some id"})

    output = service._call(operation, body)
    expected_output = {}
    assert expected_output == json.loads(output)

def test_server_call_raises_on_deserialize_failure():
    service = basic_service()

    @service.operation("echo")
    def func(value):
        return value

    operation = "operation_name"
    body = '{"name": [],}}'

    with pytest.raises(ValueError):
        service._call(operation, body)

def test_server_call_raises_on_serialize_failure():
    service = basic_service()

    @service.operation("echo")
    def func(value):
        return NameError

    operation = "echo"
    body = json.dumps({"value": "some value"})

    # json.encoder throws TypeError: <type 'NameError'> is not JSON serializable
    with pytest.raises(TypeError):
        service._call(operation, body)

def test_service_handler_invoked():
    service = basic_service()
    value1, value2 = "Hello", "World"
    values = {"value1": value1, "value2": value2}

    @service.operation("multiecho")
    def func(value1, value2):
        return value1, value2

    @extension
    def capture(context):
        captured_context["input"] = dict(context["input"])
        yield
        captured_context["output"] = dict(context["output"])
    captured_context = {}
    service.add_extension(capture())

    operation = "multiecho"
    body = json.dumps(values)

    output = json.loads(service._call(operation, body))
    result1, result2 = output["value1"], output["value2"]

    # Handler doesn't mess with return unpacking
    assert (result1, result2) == (value1, value2)

    # Handler captures input/output
    assert values == captured_context["input"]
    assert values == captured_context["output"]

def test_service_handler_exception_returned():
    # Exceptions thrown from any part of the request chain,
    # including (especially) any handler,
    # should be returned to the client through the normal exception
    # packing process - not just exceptions during the underlying
    # function's operation.
    service = basic_service()
    value = {"value": "hello"}

    @service.operation("echo")
    def func(value):
        return value

    @extension
    def raiser(context):
        raise service.ex.WhitelistedException("arg1", True)
    service.add_extension(raiser())

    operation = "echo"
    body = json.dumps({"value": value})

    output = service._call(operation, body)
    assert is_exception(output, "WhitelistedException")

def test_service_validate_missing_func():
    service = basic_service()

    @service.operation("echo")
    def operation(value):
        return value

    with pytest.raises(ValueError):
        service.validate()

#===========================
#
# Extension (Client/Server)
#
#===========================

def test_Extension_no_register():
    class Registry(object):
        extensions = []
        def add_extension(self, extension):
            self.extensions.append(extension)

    registry = Registry()
    extension = Extension()
    assert extension not in registry.extensions

def test_Extension_register():
    class Registry(object):
        extensions = []
        def add_extension(self, extension):
            self.extensions.append(extension)

    registry = Registry()
    extension = Extension(registry)
    assert extension in registry.extensions

def test_Extension_before_operation():
    client = basic_client()
    service = basic_service()
    client.handler = DirectClientHandler(service)

    @service.operation("echo")
    def operation(value):
        return value

    class BeforeExtension(Extension):
        def before_operation(self, operation, next_handler):
            self.operation = operation
            next_handler(operation)

    client_before = BeforeExtension(client)
    service_before = BeforeExtension(service)
    assert "foo" == client.echo("foo")
    assert "echo" == client_before.operation
    assert "echo" == service_before.operation

def test_Extension_after_operation():
    client = basic_client()
    service = basic_service()
    client.handler = DirectClientHandler(service)

    @service.operation("echo")
    def operation(value):
        return value

    class AfterExtension(Extension):
        def after_operation(self, operation, next_handler):
            self.operation = operation
            next_handler(operation)

    client_after = AfterExtension(client)
    service_after = AfterExtension(service)
    assert "foo" == client.echo("foo")
    assert "echo" == client_after.operation
    assert "echo" == service_after.operation

#===========================
#
# End-to-end tests
#
#===========================

def test_e2e_no_return():
    client = basic_client()
    service = basic_service()
    client.handler = DirectClientHandler(service)

    called = [False]
    @service.operation("signal")
    def operation(exec_id):
        called[0] = True

    assert None == client.signal("foo")
    assert called[0]

def test_e2e_single_return():
    client = basic_client()
    service = basic_service()
    client.handler = DirectClientHandler(service)

    called = [False]
    @service.operation("echo")
    def operation(value):
        called[0] = True
        return value

    for value in ["foo", None, False, -1]:
        called[0] = False
        assert value == client.echo(value)
        assert called[0]

def test_e2e_multiple_return():
    client = basic_client()
    service = basic_service()
    client.handler = DirectClientHandler(service)

    called = [False]
    @service.operation("multiecho")
    def operation(value1, value2):
        called[0] = True
        return value1, value2

    for (value1, value2) in [(False, True), (None, "foo"), (None, None), (-1, 5)]:
        called[0] = False
        assert [value1, value2] == client.multiecho(value1, value2)
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
    return DumbWireHandler(result)

def mock_bottle(string=""):
    '''Sets (mocked)bottle.request.body = IOBytes of string'''
    mock_bottle = Container()
    mock_bottle.abort = bottle.abort
    mock_bottle.request = Container()
    mock_bottle.request.body = six.BytesIO(six.b(string))
    return mock_bottle


class Container(object): pass

def is_exception(string, exception_cls):
    data = json.loads(string)
    return exception_cls == data["__exception"]["cls"]


class RaiseClientHandler(ClientHandler):
    def handle(self, service, operation, data, **kwargs):
        raise Exception("wire handler raised")


class MalformedClientHandler(ClientHandler):
    def handle(self, service, operation, data, **kwargs):
        return '{"name": [,}'


class DirectClientHandler(ClientHandler):
    def __init__(self, service):
        self.service = service

    def handle(self, service, operation, data, **kwargs):
        return self.service._call(operation, data)


class DumbWireHandler(ClientHandler):
    def __init__(self, result):
        self.result = result

    def handle(self, service_name, operation, data, **kwargs):
        return self.result
