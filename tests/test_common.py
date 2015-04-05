import pytest
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


def test_container_missing():
    container = common.Container()
    assert container.missing is None
