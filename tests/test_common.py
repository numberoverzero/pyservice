import pytest
import ujson
from pyservice import common


def test_load_defaults_deep_copy():
    '''
    When copying defaults, structures shouldn't be shallow copies
    '''
    empty_api = {}
    common.load_defaults(empty_api)
    assert empty_api["endpoint"] is not common.DEFAULT_API["endpoint"]


def test_construct_client_pattern():
    '''
    Should create a format string that can be used to dispatch operations
    '''

    endpoint = {
        "scheme": "scheme",
        "host": "host",
        "port": "port",
        "pattern": "/pattern"
    }
    common.construct_client_pattern(endpoint)
    assert endpoint["client_pattern"] == "scheme://host:port/pattern"


def test_construct_invalid_client_pattern():
    '''
    Should raise ValueError when a portion of the endpoint is missing
    '''

    endpoint = {
        "scheme": "scheme",
        "port": "port",
        "pattern": "/pattern"
    }
    with pytest.raises(ValueError):
        common.construct_client_pattern(endpoint)


def test_construct_service_pattern():
    '''
    Should create a regex that can be used to dispatch operations
    '''

    endpoint = {
        "scheme": "scheme",
        "host": "host",
        "port": "port",
        "pattern": "/api/{operation}/suffix"
    }
    common.construct_service_pattern(endpoint)
    match = endpoint["service_pattern"].match("/api/foo/suffix")

    assert match
    assert match.groupdict()["operation"] == "foo"


def test_construct_invalid_service_pattern():
    '''
    Should raise ValueError when pattern is missing
    '''

    endpoint = {
        "scheme": "scheme",
        "host": "host",
        "port": "port"
    }
    with pytest.raises(ValueError):
        common.construct_service_pattern(endpoint)


def test_deserialize_replaces_existing_keys():
    ''' deserialize should replace any existing values when loading '''
    container = {"key": "value"}
    string = ujson.dumps({"key": "value2", "other": "value"})
    common.deserialize(string, container)

    assert container["key"] == "value2"
    assert container["other"] == "value"


def test_serialize_aliases_dumps():
    ''' serialize is an alias for `dumps` to mirror deserialize '''
    container = {"key": "value"}
    same_container = ujson.loads(common.serialize(container))
    assert container == same_container


def test_serialize_container():
    ''' serialize should work on containers '''
    container = common.Container()
    container.foo = "bar"

    same_container = ujson.loads(common.serialize(container))
    assert container == same_container


def test_container_clobbers_dict_methods():
    ''' No respect for existing methods on dicts '''
    container = common.Container()
    real_keys_method = container.keys

    container.keys = "Now it's a string"
    assert container.keys is not real_keys_method
    assert container.keys == "Now it's a string"


def test_container_get():
    ''' Container.foo aliases Container["foo"] '''
    container = common.Container()
    container["foo"] = object()
    assert container.foo is container["foo"]


def test_container_set():
    ''' Container.foo aliases Container["foo"] '''
    container = common.Container()
    container.foo = object()
    assert container.foo is container["foo"]


def test_container_missing():
    ''' missing keys return None, and are not persisted '''
    container = common.Container()
    assert container.missing_key is None
    assert "missing_key" not in container


def test_context_calls_processor():
    ''' context.process_request continues processing '''
    class Processor:
        def __init__(self):
            self.calls = 0

        def continue_execution(self):
            self.calls += 1

    processor = Processor()
    context = common.Context(processor)
    context.process_request()
    context.process_request()
    assert processor.calls == 2


def test_exception_factory_consistent_values():
    ''' exception classes must be the same class object every call '''
    factory = common.ExceptionFactory()
    assert factory.BadFoo is factory.BadFoo


def test_exception_factory_defers_to_builtins():
    ''' builtin exceptions are returned directly, not shadowed '''
    factory = common.ExceptionFactory()
    assert factory.ValueError is ValueError


def test_exception_factory_caches_attributes():
    ''' getattr should never be called twice for the same exception class '''
    calls = 0

    class Observer(common.ExceptionFactory):
        def __getattr__(self, name):
            nonlocal calls
            calls += 1
            return super().__getattr__(name)

    factory = Observer()
    assert factory.FooException is factory.FooException
    assert calls == 1
