"""
request body parsing logic and WSGIRefServer derived from bottle.py
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

from io import BytesIO
from tempfile import TemporaryFile


def tob(s, enc='utf8'):
    return s.encode(enc) if isinstance(s, unicode) else bytes(s)


def touni(s, enc='utf8', err='strict'):
    if isinstance(s, bytes):
        return s.decode(enc, err)
    else:
        return unicode(s or ("" if s is None else s))


class RequestException(Exception):
    def __init__(self, status, msg):
        self.status = status
        self.msg = msg


MEMFILE_MAX = 102400
REQUEST_TOO_LARGE = RequestException(413, 'Request too large')
BAD_CHUNKED_BODY = RequestException(
    400, 'Error while parsing chunked transfer body')


def path(environ):
    return environ['PATH_INFO']


def content_length(environ):
    return int(environ.get('CONTENT_LENGTH') or -1)


def chunked_body(environ):
    return environ.get('HTTP_TRANSFER_ENCODING', '').lower()


def body(environ):
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
    chunked = chunked_body(environ)
    body_iter = _iter_chunked if chunked else _iter_body
    read_func = environ['wsgi.input'].read
    try:
        body, body_size, is_temp_file = BytesIO(), 0, False
        for part in body_iter(read_func, MEMFILE_MAX, environ):
            body.write(part)
            body_size += len(part)
            if not is_temp_file and body_size > MEMFILE_MAX:
                body, tmp = TemporaryFile(mode='w+b'), body
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
    rn, sem, bs = tob('\r\n'), tob(';'), tob('')
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
            maxread = int(touni(size.strip()), 16)
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
