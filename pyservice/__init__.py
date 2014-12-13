"""
Copyright (c) 2014, Joseph Cross.

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
__all__ = ["Client", "Service"]

import builtins
import functools
import http.client
import io
import logging
import re
import requests
import tempfile
import ujson


class RequestException(Exception):
    def __init__(self, status):
        self.status = status


LOGGER = logging.getLogger(__name__)
DEFAULT_API = {
    "version": "0",
    "timeout": 60,
    "debug": False,
    "endpoint": {
        "scheme": "https",
        "host": "localhost",
        "port": 8080,
        "path": "/api/{version}/{operation}"
    },
    "operations": [],
    "exceptions": []
}
MEMFILE_MAX = 102400
HTTP_CODES = {i[0]: "{} {}".format(*i) for i in http.client.responses.items()}
REQUEST_TOO_LARGE = RequestException(413)
BAD_CHUNKED_BODY = RequestException(400)
INTERNAL_ERROR = RequestException(500)
UNKNOWN_OPERATION = RequestException(404)


# ================
# Utility
# ================

def copy_missing(dst, src):
    """Copy any keys in `src` to `dst` that are missing in `dst`"""
    for key, value in src.items():
        dst[key] = dst.get(key, value)


def compute_uri(api, consumer):
    if consumer is Client:
        uri = "{scheme}://{host}:{port}{path}".format(**api["endpoint"])
    else:  # consumer is Service:
        uri = api["endpoint"]["path"]
    api["uri"] = uri.format(operation="{operation}", **api)


def serialize(container):
    return ujson.dumps(container)


def deserialize(string, container):
    container.update(ujson.loads(string))


def abort(status=500):
    # Allows things like abort(INTERNAL_ERROR)
    if isinstance(status, RequestException):
        raise status
    # Create exception and raise
    raise RequestException(status)


def is_request_exception(response):
    return 400 <= response.status_code < 600


def build_pattern(string):
    '''
    string is a python format string with version and operation keys.
    For example: "/api/v1/{operation}"
    '''
    # Replace {operation} so that we can route an incoming request
    string = string.format(operation="(?P<operation>[^/]+)")
    # Ignore trailing slash, match exact string only
    return re.compile("^{}/?$".format(string))


def load_operation(pattern, environ):
    path = environ['PATH_INFO']
    match = pattern.search(path)
    if not match:
        abort(UNKNOWN_OPERATION)
    return match.groupdict()["operation"]


class WriteOnly(object):
    def __init__(self, func):
        self.func = func

    def __set__(self, obj, value):
        self.func(obj, value)


class Context(object):
    def __init__(self, operation, processor):
        self.operation = operation
        self.__processor__ = processor

    def process_request(self):
        self.__processor__.continue_execution()


class Container(dict):
    """
    Not using defaultdict since we don't want to store accessed keys -
    both for space considerations and iterating over keys.
    """
    def __init__(self):
        super().__init__()

    def __missing__(self, key):
        return None

    def __getattr__(self, name):
        return self[name]

    def __setattr__(self, name, value):
        self[name] = value


class ExceptionFactory(object):
    '''
    Class for building and storing Exception types.
    Built-in exception names are reserved.
    '''
    def __init__(self):
        self.classes = {}

    def build_exception_class(self, name):
        self.classes[name] = type(name, (Exception,), {})
        return self.classes[name]

    def get_class(self, name):
        # Check builtins for real exception class
        cls = getattr(builtins, name, None)
        # Cached?
        if not cls:
            cls = self.classes.get(name, None)
        # Cache
        if not cls:
            cls = self.build_exception_class(name)
        return cls

    def exception(self, name, *args):
        return self.get_class(name)(*args)

    def __getattr__(self, name):
        return self.get_class(name)


# ================
# Client
# ================

class Client(object):
    def __init__(self, **api):
        copy_missing(api, DEFAULT_API)
        compute_uri(api, Client)
        self.api = api

        self.plugins = []
        self.exceptions = ExceptionFactory()

    def __getattr__(self, operation):
        if operation not in self.api["operations"]:
            raise ValueError("Unknown operation '{}'".format(operation))
        return functools.partial(self, operation=operation)

    def plugin(self, func):
        self.plugins.append(func)
        return func

    def __call__(self, operation, **request):
        '''Entry point for remote calls'''
        return ClientProcessor(self, operation, request).execute()


class ClientProcessor(object):
    def __init__(self, client, operation, request):
        self.client = client
        self.operation = operation

        self.context = Context(operation, self)
        self.context.client = client
        self.request = Container()
        self.request.update(request)
        self.request_body = None
        self.response = Container()
        self.response_body = None

        self.index = -1

    def execute(self):
        self.continue_execution()
        return self.response

    def continue_execution(self):
        self.index += 1
        plugins = self.client.plugins
        n = len(plugins)

        if self.index == n:
            # Last plugin of this type, package args and invoke remote call
            self.remote_call()
        # index < n
        elif self.index < n:
            plugins[self.index](self.request, self.response, self.context)
        else:
            # BUG - index > n means processor ran index over plugin length
            raise ValueError("Bug in pyservice.ClientProcessor!")

    def remote_call(self):
        self.request_body = serialize(self.request)

        uri = self.client.api["uri"].format(operation=self.operation)
        data = self.request_body
        timeout = self.client.api["timeout"]
        response = requests.post(uri, data=data, timeout=timeout)

        self.handle_http_errors(response)
        self.response_body = response.text
        deserialize(self.response_body, self.response)
        self.handle_service_exceptions()

    def handle_http_errors(self, response):
        if is_request_exception(response):
            message = "{} {}".format(response.status_code, response.reason)
            self.raise_exception({
                "cls": "RequestException",
                "args": (message,)
            })

    def handle_service_exceptions(self):
        exception = self.response.get("__exception__", None)
        if exception:
            # Don't leak incomplete operation state
            self.response.clear()
            self.raise_exception(exception)

    def raise_exception(self, exception):
        name = exception["cls"]
        args = exception["args"]
        exception = getattr(self.client.exceptions, name)(*args)
        raise exception


# ================
# Service
# ================


class Service(object):
    def __init__(self, **api):
        copy_missing(api, DEFAULT_API)
        compute_uri(api, Service)
        self.api = api
        self.pattern = build_pattern(self.api["uri"])

        # TODO: Add operation filtering
        self.plugins = {
            "request": [],
            "operation": []
        }
        self.functions = {}
        self.exceptions = ExceptionFactory()

    def plugin(self, scope, *, func=None):
        if scope not in ["request", "operation"]:
            raise ValueError("Unknown scope {}".format(scope))
        # Return decorator that takes function
        if not func:
            return lambda func: self.plugin(scope=scope, func=func)
        self.plugins[scope].append(func)
        return func

    def operation(self, name, *, func=None):
        if name not in self.api["operations"]:
            raise ValueError("Unknown operation {}".format(name))
        # Return decorator that takes function
        if not func:
            return lambda func: self.operation(name=name, func=func)
        self.functions[name] = func
        return func

    def wsgi_application(self, environ, start_response):
        response = Response(start_response)
        try:
            # Load operation name from path, abort if
            # there's nothing there.
            operation = load_operation(self.pattern, environ)
            if operation not in self.api["operations"]:
                abort(UNKNOWN_OPERATION)
            request_body = load_body(environ)
            processor = ServiceProcessor(self, operation, request_body)
            response.body = processor.execute()
        # service should be serializing interal exceptions
        except Exception as exception:
            LOGGER.debug("Exception during wsgi call:", exc_info=exception)
            # Defined failure case -
            # invalid body, unknown path/operation
            if isinstance(exception, RequestException):
                response.exception(exception)
            # Unexpected failure type
            else:
                response.exception(INTERNAL_ERROR)
        finally:
            return response.send()


class ServiceProcessor(object):
    def __init__(self, service, operation, request_body):
        self.service = service
        self.operation = operation

        self.context = Context(operation, self)
        self.context.service = service
        self.request = Container()
        self.request_body = request_body
        self.response = Container()
        self.response_body = None

        self.state = "request"  # request -> operation -> function
        self.index = -1

    def execute(self):
        if self.state is None:
            raise ValueError("Already processed request")
        try:
            self.continue_execution()
            return self.response_body
        except Exception as exception:
            self.raise_exception(exception)
            return self.response_body

    def continue_execution(self):
        self.index += 1
        plugins = self.service.plugins[self.state]
        n = len(plugins)

        if self.index == n:
            # Last plugin of this type, either roll over to the next plugin
            # type, or invoke the function underneath it all
            if self.state == "request":
                self.index = -1
                self.state = "operation"

                deserialize(self.request_body, self.request)
                self.continue_execution()
                self.response_body = serialize(self.response)
            elif self.state == "operation":
                func = self.service.functions[self.operation]
                func(self.request, self.response, self.context)
                self.state = None
        # index < n
        elif self.index < n:
            if self.state == "request":
                plugins[self.index](self.context)
            elif self.state == "operation":
                plugins[self.index](self.request, self.response, self.context)
        else:
            # BUG - index > n means processor ran index over plugin length
            abort(INTERNAL_ERROR)

    def raise_exception(self, exception):
        name = exception.__class__.__name__
        args = exception.args

        # Don't let non-whitelisted exceptions escape if we're not debugging
        whitelisted = name in self.service.api["exceptions"]
        debugging = self.service.api["debug"]
        if not whitelisted and not debugging:
            abort(INTERNAL_ERROR)

        # Don't leak incomplete operation state
        self.response.clear()
        self.response["__exception__"] = {
            "cls": name,
            "args": args
        }
        self.response_body = serialize(self.response)


# ================
# Response + WSGI
# ================


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


class Response(object):
    def __init__(self, start_response):
        self.status = 200
        self.body = ''
        self.start_response = start_response

    def exception(self, exc):
        '''Set appropriate status and message for a RequestException'''
        self.status = exc.status
        self.body = ''

    @WriteOnly
    def status(self, value):
        self._status = HTTP_CODES[value]

    @WriteOnly
    def body(self, value):
        '''Must be a unicode string'''

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
    return int(environ.get('CONTENT_LENGTH') or -1)


def chunked_body(environ):
    return environ.get('HTTP_TRANSFER_ENCODING', '').lower()


def load_body(environ):
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
