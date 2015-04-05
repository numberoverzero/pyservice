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
