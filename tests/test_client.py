import pytest
from pyservice import Client


def test_load_api_defaults():
    ''' Missing api values are loaded '''
    api = {
        "version": "2.0",
        "not_provided": "value",
        "operations": ["foo"]
    }
    service = Client(**api)

    # Ensure given values aren't blown away
    for key, value in api.items():
        assert service.api[key] == value

    expected_keys = [
        "version",
        "timeout",
        "debug",
        "endpoint",
        "operations",
        "exceptions"
    ]
    for key in expected_keys:
        assert key in service.api


def test_client_builds_path_format():
    '''
    endpoint.client_pattern should be a format string containing {operation}
    '''
    api = {"endpoint": {
        "pattern": "/test/{operation}",
        "scheme": "http",
        "host": "localhost",
        "port": 8080
        }
    }
    service = Client(**api)
    pattern = service.api["endpoint"]["client_pattern"]
    assert pattern == "http://localhost:8080/test/{operation}"


def test_client_no_plugins(client):
    ''' no built-in plugins '''
    assert not client.plugins["request"]
    assert not client.plugins["operation"]


def test_client_dynamic_exceptions(client):
    ''' client provides a dynamic exception factory '''
    assert client.exceptions.FooError
    assert client.exceptions.ValueError is ValueError


def test_unknown_plugin_scope(client):
    ''' request and operation are the only scopes '''
    with pytest.raises(ValueError):
        client.plugin(scope="not a real scope")


def test_plugin_binding(client):
    ''' func can be passed to client.plugin or deferred '''
    def plugin():
        pass

    client.plugin(scope='request', func=plugin)

    def another_plugin():
        pass

    client.plugin(scope='operation')(another_plugin)

    assert plugin in client.plugins['request']
    assert another_plugin in client.plugins['operation']


def test_client_unknown_operation(client):
    ''' ValueError for an unknown operation '''
    with pytest.raises(ValueError):
        client.operation("unknown operation")


def test_operation_binding_caches(api, observe):
    ''' operation lookup is cached '''
    class ObserverClient(Client):
        def __getattr__(self, *args, **kwargs):
            nonlocal calls
            calls += 1
            return super().__getattr__(*args, **kwargs)

    client = ObserverClient(**api)
    calls = 0

    client.foo
    client.foo

    assert calls == 1


def test_operation_calls_process(client):
    return_value = "Hello, World!"
    process_args = []

    def process(*args):
        nonlocal process_args, return_value
        process_args.extend(args)
        return return_value
    client.__process__ = process

    result = client.foo(key="value")
    assert result == return_value
    assert process_args == ["foo", {"key": "value"}]
