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
    ''' Throw when the operation name isn't in the api '''
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


def test_wsgi_application(service, environment, start_response):
    '''
    process has the correct args
    body is serialized
    headers are correct
    '''
    body = "body"
    return_value = "Hello, World!"
    process_args = []

    def process(*args):
        nonlocal process_args, return_value
        process_args.extend(args)
        return return_value
    service.__process__ = process

    environ = environment(body, len(body))
    environ["PATH_INFO"] = "/test/foo"

    result = service.wsgi_application(environ, start_response)
    assert result == [bytes(return_value, 'utf8')]
    assert process_args == [service, "foo", body]
    assert start_response.status == '200 OK'
    assert start_response.headers == [('Content-Length',
                                       str(len(return_value)))]


def test_wsgi_unknown_operation(service, environment, start_response):
    ''' Response is 404 when operation is unknown '''
    def process(*args):
        return "Not Used"
    service.__process__ = process

    environ = environment("", 0)
    environ["PATH_INFO"] = "/test/not_an_operation"

    result = service.wsgi_application(environ, start_response)
    assert result == [b'']
    assert start_response.status == '404 Not Found'
    assert start_response.headers == [('Content-Length', '0')]


def test_wsgi_unknown_exception(service, environment, start_response):
    ''' Response is 500 Internal Error when unexpected exception occurrs '''
    def process(*args):
        raise RuntimeError("Unexpected")
    service.__process__ = process

    environ = environment("", 0)
    environ["PATH_INFO"] = "/test/foo"

    result = service.wsgi_application(environ, start_response)
    assert result == [b'']
    assert start_response.status == '500 Internal Server Error'
    assert start_response.headers == [('Content-Length', '0')]
