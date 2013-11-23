import six
import json
import pytest
import tempfile
from contextlib import contextmanager
from collections import defaultdict

from pyservice.exception_factory import ExceptionFactory
from pyservice.description import validate_name, parse_metadata, default_field, Description, ServiceDescription, OperationDescription
from pyservice.layer import Layer, Stack
from pyservice.serialize import JsonSerializer, to_list, to_dict
from pyservice.util import cached, cached_property

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

    with pytest.raises(ValueError):
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
