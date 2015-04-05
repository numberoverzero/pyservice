import pytest
from pyservice import Service, wsgi


@pytest.fixture
def api():
    ''' Very Simple API - no operations '''
    return {
        "endpoint": {
            "scheme": "http",
            "pattern": "/test/{operation}",
            "host": "localhost",
            "port": 8080
        },
        "operations": ["foo"]
    }


@pytest.fixture
def service(api):
    ''' Return a service with a simple api '''
    return Service(**api)


def test_request_known_operation(service):
    '''
    Correctly matches against PATH_INFO and validates operation is in service
    '''
    environ = {"PATH_INFO": "/test/foo"}
    request = wsgi.Request(service, environ)
    assert request.operation == "foo"


def test_request_unknown_operation(service):
    ''' Throw when operation isn't expected '''
    environ = {"PATH_INFO": "/test/not_foo"}
    request = wsgi.Request(service, environ)
    with pytest.raises(wsgi.RequestException):
        request.operation


def test_request_bad_path(service):
    ''' Throw when uri doesn't match service pattern '''
    environ = {"PATH_INFO": "/not/correct"}
    request = wsgi.Request(service, environ)
    with pytest.raises(wsgi.RequestException):
        request.operation
