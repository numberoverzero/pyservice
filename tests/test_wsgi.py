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


@pytest.fixture
def start_response():
    ''' Function that stores status, headers on itself '''
    def func(status, headers):
        self.status = status
        self.headers = headers
    self = func

    return func


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


def test_default_response(start_response):
    ''' By default responses should be 500s with no body '''
    response = wsgi.Response(start_response)

    response_body = response.send()[0]
    assert start_response.status == '500 Internal Server Error'
    assert start_response.headers == [('Content-Length', '0')]
    assert not response_body


def test_set_response_ok(start_response):
    ''' 200 OK without a body is fine '''
    response = wsgi.Response(start_response)
    response.status = 200

    response_body = response.send()[0]
    assert start_response.status == '200 OK'
    assert start_response.headers == [('Content-Length', '0')]
    assert not response_body


def test_set_response_exception(start_response):
    ''' Setting an exception should clear the body '''
    response = wsgi.Response(start_response)
    response.body = "This will be cleared"
    exception = wsgi.RequestException(404)
    response.exception(exception)

    response_body = response.send()[0]
    assert start_response.status == '404 Not Found'
    assert start_response.headers == [('Content-Length', '0')]
    assert not response_body


def test_set_response_body(start_response):
    ''' Body is correctly returned, and appropriate header values are set '''
    response = wsgi.Response(start_response)
    response.status = 400  # Setting a body will clear this
    response.body = "This is the body"

    response_body = response.send()[0]
    assert start_response.status == '200 OK'
    assert start_response.headers == [('Content-Length', '16')]
    assert response_body == b'This is the body'


def test_set_response_unicode(start_response):
    ''' ಠ_ಠ '''
    response = wsgi.Response(start_response)
    response.body = "ಠ_ಠ"

    response_body = response.send()[0]
    assert response_body == b'\xe0\xb2\xa0_\xe0\xb2\xa0'
