import pytest
from pyservice import Service


def test_load_api_defaults():
    ''' Missing api values are loaded '''
    api = {
        "version": "2.0",
        "not_provided": "value",
        "operations": ["foo"]
    }
    service = Service(**api)

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


def test_service_builds_regex():
    ''' endpoint.service_pattern should match wsgi path '''
    api = {"endpoint": {"pattern": "/test/{operation}"}}
    service = Service(**api)
    pattern = service.api["endpoint"]["service_pattern"]
    match = pattern.match("/test/operation_name")

    assert match.groupdict()["operation"] == "operation_name"


def test_service_no_plugins(service):
    ''' no built-in plugins '''
    assert not service.plugins["request"]
    assert not service.plugins["operation"]


def test_service_dynamic_exceptions(service):
    ''' service provides a dynamic exception factory '''
    assert service.exceptions.FooError
    assert service.exceptions.ValueError is ValueError


def test_unknown_plugin_scope(service):
    ''' request and operation are the only scopes '''
    with pytest.raises(ValueError):
        service.plugin(scope="not a real scope")


def test_plugin_binding(service):
    ''' func can be passed to service.plugin or deferred '''
    def plugin():
        pass

    service.plugin(scope='request', func=plugin)

    def another_plugin():
        pass

    service.plugin(scope='operation')(another_plugin)

    assert plugin in service.plugins['request']
    assert another_plugin in service.plugins['operation']


def test_service_unknown_decorator(service):
    with pytest.raises(ValueError):
        service.operation("unknown operation")


def test_operation_binding(service):
    ''' func can be passed to service.operation or deferred '''
    def operation():
        pass

    service.operation('foo', func=operation)

    def another_operation():
        pass

    service.operation('bar')(another_operation)

    assert operation is service.functions['foo']
    assert another_operation is service.functions['bar']
