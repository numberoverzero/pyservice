import io
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


def test_content_length_not_specified():
    ''' By default content length should be -1 '''
    environ = {}
    assert wsgi.content_length(environ) == -1


def test_content_length_returns_int():
    ''' CONTENT_LENGTH is converted to an int '''
    environ = {"CONTENT_LENGTH": "5"}
    assert wsgi.content_length(environ) == 5


def test_chunked_body_missing():
    ''' By default chunked is False '''
    environ = {}
    assert not wsgi.chunked_body(environ)


def test_body_not_chunked():
    ''' Non-empty body that doesn't include 'chunked' '''
    environ = {"HTTP_TRANSFER_ENCODING": "utf8"}
    assert not wsgi.chunked_body(environ)


def test_chunked_body_ignores_case():
    ''' chunked is equivalent to CHUNKED '''
    environ = {"HTTP_TRANSFER_ENCODING": "CHUNKed"}
    assert wsgi.chunked_body(environ)


def test_chunked_body_matches_any_substr():
    ''' chunked can appear anywhere in the encoding '''
    environ = {"HTTP_TRANSFER_ENCODING": "this is chunked?! ಠ_ಠ"}
    assert wsgi.chunked_body(environ)


def test_load_body_max_size():
    ''' load_body raises when CONTENT_LENGTH is too large '''
    environ = {"CONTENT_LENGTH": wsgi.MEMFILE_MAX + 1}
    with pytest.raises(wsgi.RequestException):
        wsgi.load_body(environ)


def test_load_body_no_length_header():
    '''
    load_body raises when CONTENT_LENGTH is missing
    and HTTP_TRANSFER_ENCODING isn't chunked
    '''
    environ = {
        "wsgi.input": io.BytesIO(b"None of this will be returned")
    }
    with pytest.raises(wsgi.RequestException):
        wsgi.load_body(environ)


def test_load_partial_buffer():
    ''' don't load more than CONTENT_LENGTH bytes '''
    environ = {
        "wsgi.input": io.BytesIO(b"Only this|None of this"),
        "CONTENT_LENGTH": "9"
    }
    body = wsgi.load_body(environ)
    assert body == "Only this"


def test_load_extra_buffer():
    ''' don't read past the available buffer '''
    environ = {
        "wsgi.input": io.BytesIO(b"Only this"),
        "CONTENT_LENGTH": wsgi.MEMFILE_MAX
    }
    body = wsgi.load_body(environ)
    assert body == "Only this"


def test_load_body_reentrant():
    ''' call load_body multiple times '''
    environ = {
        "wsgi.input": io.BytesIO(b"Only this"),
        "CONTENT_LENGTH": "9"
    }
    body = wsgi.load_body(environ)
    same_body = wsgi.load_body(environ)
    assert body == "Only this"
    assert body == same_body


def test_load_body_no_input():
    ''' load_body returns an empty string when wsgi.input is missing '''
    environ = {"CONTENT_LENGTH": "100"}
    assert not wsgi.load_body(environ)


def test_load_empty_chunked_body():
    ''' load an empty chunked body '''
    environ = {
        "wsgi.input": io.BytesIO(b"0\r\n"),
        "HTTP_TRANSFER_ENCODING": "chunked"
    }
    assert wsgi.load_body(environ) == ""


def test_load_chunked_body_multiple_chunks():
    ''' load a chunked body in two chunks'''
    environ = {
        "wsgi.input": io.BytesIO(b"1\r\na\r\n2\r\nbb\r\n0\r\n"),
        "HTTP_TRANSFER_ENCODING": "chunked"
    }
    assert wsgi.load_body(environ) == "abb"


def test_load_chunked_body_not_terminated():
    ''' various invalid chunked bodies'''
    invalid_bodies = [
        b"1\r\n",  # Not terminated with 0\r\n
        b"1",      # Missing \r\n and 0\r\n
        b"j\r\n",  # Illegal header size character
        b"1\r\n0",  # Missing \r\n
        bytes("f"*(wsgi.MEMFILE_MAX + 1) + "\r\n", 'utf8')  # Header too large
    ]
    for invalid_body in invalid_bodies:
        environ = {
            "wsgi.input": io.BytesIO(invalid_body),
            "HTTP_TRANSFER_ENCODING": "chunked"
        }
        with pytest.raises(wsgi.RequestException):
            wsgi.load_body(environ)
