import http.client
import io
import tempfile


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

REQUEST_TOO_LARGE = RequestException(413)
BAD_CHUNKED_BODY = RequestException(400)
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
    def body(self):  # pragma: no cover
        return load_body(self.environ)


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
    if clen > MEMFILE_MAX:
        raise REQUEST_TOO_LARGE
    if clen < 0:
        clen = MEMFILE_MAX + 1
    data = _body(environ).read(clen)
    if len(data) > MEMFILE_MAX:
        raise REQUEST_TOO_LARGE
    return data.decode("UTF-8")


def _body(environ):
    try:
        read_func = environ['wsgi.input'].read
    except KeyError:
        # If there's no input we don't need to do any chunking, etc
        environ['wsgi.input'] = io.BytesIO()
        return environ['wsgi.input']
    chunked = chunked_body(environ)
    body_iter = _iter_chunked if chunked else _iter_body
    try:
        body, body_size, is_temp_file = io.BytesIO(), 0, False
        for part in body_iter(read_func, MEMFILE_MAX, environ):
            body.write(part)
            body_size += len(part)
            if not is_temp_file and body_size > MEMFILE_MAX:
                body, tmp = tempfile.TemporaryFile(mode='w+b'), body
                body.write(tmp.getvalue())
                del tmp
                is_temp_file = True
        environ['wsgi.input'] = body
        body.seek(0)
        return body
    except RequestException:
        # Probably BAD_CHUNKED_BODY
        body.close()
        raise


def _iter_body(read, bufsize, environ):
    clen = content_length(environ)
    maxread = max(0, clen)
    while maxread:
        part = read(min(maxread, bufsize))
        if not part:
            break
        yield part
        maxread -= len(part)


def _iter_chunked(read, bufsize, environ):
    rn, sem, bs = b'\r\n', b';', b''
    while True:
        header = read(1)
        while header[-2:] != rn:
            c = read(1)
            header += c
            if not c:
                raise BAD_CHUNKED_BODY
            if len(header) > bufsize:
                raise BAD_CHUNKED_BODY
        size, _, _ = header.partition(sem)
        try:
            maxread = int(size.strip(), 16)
        except ValueError:
            raise BAD_CHUNKED_BODY
        if maxread == 0:
            break
        buff = bs
        while maxread > 0:
            if not buff:
                buff = read(min(maxread, bufsize))
            part, buff = buff[:maxread], buff[maxread:]
            if not part:
                raise BAD_CHUNKED_BODY
            yield part
            maxread -= len(part)
        if read(2) != rn:
            raise BAD_CHUNKED_BODY
