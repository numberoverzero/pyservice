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

    assert match
    assert match.groupdict()["operation"] == "operation_name"


def test_service_no_plugins(service):
    ''' no built-in plugins '''
    assert not service.plugins["request"]
    assert not service.plugins["operation"]


def test_service_dynamic_exceptions(service):
    ''' service provides a dynamic exception factory '''
    assert service.exceptions.FooError
    assert service.exceptions.ValueError is ValueError
