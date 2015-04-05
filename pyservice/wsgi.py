import http.client


class setter(object):
    """ Write-only property. """
    def __init__(self, func):
        self.func = func

    def __set__(self, obj, value):
        return self.func(obj, value)


class RequestException(Exception):
    """Not visible to plugins or client/service consumers."""
    def __init__(self, status):
        self.status = status

MISSING = object()
LENGTH_REQUIRED = RequestException(411)
REQUEST_TOO_LARGE = RequestException(413)
INTERNAL_ERROR = RequestException(500)
UNKNOWN_OPERATION = RequestException(404)
HTTP_CODES = {i[0]: "{} {}".format(*i) for i in http.client.responses.items()}
MEMFILE_MAX = 102400


def is_request_exception(response):  # pragma: no cover
    """
    We're not using raise_for_status because we want to wrap transport
    errors and server failures into client exceptions
    """
    return 400 <= response.status_code < 600


"""
request body parsing logic derived from bottle.py
(https://github.com/defnull/bottle)

Copyright (c) 2014, Marcel Hellkamp.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""


class Request(object):
    """
    Expose operation and body for a given request and service.

    Tightly coupled to the implementation of pyservice.Service.  This is
    primarily chrome over the Service/wsgi.environ boundary, especially
    loading the request body.

    This should be the only place wsgi.load_body is called directly.
    """
    def __init__(self, service, environ):
        self.service = service
        self.environ = environ
        self._body = MISSING

    @property
    def operation(self):
        path = self.environ["PATH_INFO"]
        match = self.service.api["endpoint"]["service_pattern"].search(path)
        if not match:
            raise UNKNOWN_OPERATION
        operation = match.groupdict()["operation"]
        if operation not in self.service.api["operations"]:
                raise UNKNOWN_OPERATION
        return operation

    @property
    def body(self):
        if self._body is MISSING:
            self._body = load_body(self.environ)
        return self._body


class Response(object):
    """
    Simple class for setting response body and status.

    Any non-empty body will use status 200, while any call to
    `Response.exception` will set body to ''.

    To correctly start a response and return the WSGI expected body, use:
    `return response.send()` which will both start the response, and return
    a single-value array which contains the encoded body.

    Example:

        def wsgi_application(environ, start_response):
            response = Response(start_response)
            response.body = "Hello, World!"
            return response.send()

    """
    def __init__(self, start_response):
        self.status = 500
        self.body = ''
        self.start_response = start_response

    def exception(self, exc):
        '''Set appropriate status and body for a RequestException'''
        self.status = exc.status
        self.body = ''

    @setter
    def status(self, value):
        self._status = HTTP_CODES[value]

    @setter
    def body(self, value):
        '''MUST be a unicode string.  MUST be empty for non-200 statuses'''
        if value:
            self.status = 200

        # Unicode -> bytes
        value = value.encode('UTF-8')
        self._headers = [("Content-Length", str(len(value)))]

        # WSGI spec needs iterable of bytes
        self._body = [value]

    def send(self):
        ''' Start the response and return the raw body '''
        self.start_response(self._status, self._headers)
        return self._body


def content_length(environ):
    """ Returns the content length, or -1 if none is provided """
    return int(environ.get('CONTENT_LENGTH', -1))


def chunked_body(environ):
    """ Returns True if the transfer encoding contains the word 'chunked' """
    return "chunked" in environ.get('HTTP_TRANSFER_ENCODING', '').lower()


def load_body(environ):
    clen = content_length(environ)
    if chunked_body(environ) or clen < 0:
        raise LENGTH_REQUIRED
    if clen > MEMFILE_MAX:
        raise REQUEST_TOO_LARGE
    try:
        data = environ['wsgi.input'].read(clen)
        return data.decode("UTF-8")
    except KeyError:
        # wsgi.input is missing, return empty string
        return ""
