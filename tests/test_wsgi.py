import io
import pytest
from pyservice import wsgi


def with_body(string, length):
    ''' Return an environ with an appropriate bytes stream and given size '''
    return {
        'CONTENT_LENGTH': str(length),
        'wsgi.input': io.BytesIO(bytes(string, 'utf8'))
    }


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


def test_request_caches_body(service, observe):
    ''' Request.body caches load_body result '''
    environ = with_body("Body", 4)
    request = wsgi.Request(service, environ)

    # patch wsgi.load_body so we can watch call count
    observer = observe(wsgi, "load_body")

    request.body
    request.body

    assert len(observer.calls) == 1


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
    environ = with_body("", wsgi.MEMFILE_MAX + 1)
    with pytest.raises(wsgi.RequestException):
        wsgi.load_body(environ)


def test_load_body_no_length_header():
    ''' load_body raises when CONTENT_LENGTH is missing '''
    environ = {
        "wsgi.input": io.BytesIO(b"None of this will be returned")
    }
    with pytest.raises(wsgi.RequestException):
        wsgi.load_body(environ)


def test_load_body_partial_buffer():
    ''' don't load more than CONTENT_LENGTH bytes '''
    environ = with_body("Only this|None of this", 9)
    body = wsgi.load_body(environ)
    assert body == "Only this"


def test_load_body_extra_buffer():
    ''' don't read past the available buffer '''
    environ = with_body("Only this", wsgi.MEMFILE_MAX)
    body = wsgi.load_body(environ)
    assert body == "Only this"


def test_load_body_not_reentrant():
    ''' wsgi.input is consumed on read'''
    environ = with_body("Only this", 9)
    body = wsgi.load_body(environ)
    different_body = wsgi.load_body(environ)
    assert body == "Only this"
    assert different_body == ""


def test_load_body_no_input():
    ''' load_body returns an empty string when wsgi.input is missing '''
    environ = {"CONTENT_LENGTH": "100"}
    assert wsgi.load_body(environ) == ''


def test_load_chunked_body_raises():
    ''' chunked encoding isn't supported '''
    environ = with_body("Hello", 100)
    environ["HTTP_TRANSFER_ENCODING"] = "chunked"
    with pytest.raises(wsgi.RequestException):
        wsgi.load_body(environ)
