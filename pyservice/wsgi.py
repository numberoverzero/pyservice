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
import io
import re
import logging
import tempfile
logger = logging.getLogger(__name__)


class RequestException(Exception):
    def __init__(self, status, msg):
        self.status = status
        self.msg = msg


def abort(status=500, msg="Internal Error"):
    # Allows things like abort(INTERNAL_ERROR)
    if isinstance(status, RequestException):
        raise status
    # Create exception and raise
    raise RequestException(status, msg)


MEMFILE_MAX = 102400
REQUEST_TOO_LARGE = RequestException(413, 'Request too large')
BAD_CHUNKED_BODY = RequestException(
    400, 'Error while parsing chunked transfer body')
INTERNAL_ERROR = RequestException(500, "Internal Error")
UNKNOWN_OPERATION = RequestException(404, "Unknown Operation")


class Response(object):
    import http.client
    HTTP_CODES = dict(
        (k, "{} {}".format(k, v)) for (k, v) in http.client.responses.items())

    def __init__(self):
        self.status = 200
        self.headers = {}
        self.charset = 'UTF-8'
        self.body = ''

    def exception(self, exc):
        '''Return appropriate status and message for a RequestException'''
        self.status = exc.status
        self.body = exc.msg

    @property
    def body(self):
        '''Body as string'''
        return self._body[0].decode(self.charset)

    @body.setter
    def body(self, value):
        '''Must be a unicode string'''

        if not isinstance(value, str):
            raise INTERNAL_ERROR

        # Unicode -> bytes
        value = value.encode(self.charset)
        self.headers['Content-Length'] = len(value)

        # WSGI spec needs iterable of bytes
        self._body = [value]

    @property
    def body_raw(self):
        '''Body as formatted for return from wsgi app'''
        return self._body

    @property
    def headers_list(self):
        return [(str(h), str(v)) for (h, v) in self.headers.items()]

    @property
    def status_line(self):
        return Response.HTTP_CODES[self.status]


def build_pattern(string):
    '''
    string is a python format string with version and operation keys.
    For example: "/api/{version}/{operation}"
    '''
    matchers = {
        "version": "(?P<version>[^/]+)",
        "operation": "(?P<operation>[^/]+)"
    }
    return re.compile("^" + string.format(**matchers) + "/?$")


def path(environ):
    return environ['PATH_INFO']


def content_length(environ):
    return int(environ.get('CONTENT_LENGTH') or -1)


def chunked_body(environ):
    return environ.get('HTTP_TRANSFER_ENCODING', '').lower()


def body(environ):
    clen = content_length(environ)
    if clen > MEMFILE_MAX:
        abort(REQUEST_TOO_LARGE)
    if clen < 0:
        clen = MEMFILE_MAX + 1
    data = _body(environ).read(clen)
    if len(data) > MEMFILE_MAX:
        abort(REQUEST_TOO_LARGE)
    return data.decode("UTF-8")


def _body(environ):
    chunked = chunked_body(environ)
    body_iter = _iter_chunked if chunked else _iter_body
    read_func = environ['wsgi.input'].read
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
                abort(BAD_CHUNKED_BODY)
            if len(header) > bufsize:
                abort(BAD_CHUNKED_BODY)
        size, _, _ = header.partition(sem)
        try:
            maxread = int(size.strip(), 16)
        except ValueError:
            abort(BAD_CHUNKED_BODY)
        if maxread == 0:
            break
        buff = bs
        while maxread > 0:
            if not buff:
                buff = read(min(maxread, bufsize))
            part, buff = buff[:maxread], buff[maxread:]
            if not part:
                abort(BAD_CHUNKED_BODY)
            yield part
            maxread -= len(part)
        if read(2) != rn:
            abort(BAD_CHUNKED_BODY)
