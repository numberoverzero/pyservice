import re
import logging
from .wsgi_util import path, body, RequestException
logger = logging.getLogger(__name__)


def build_pattern(string):
    '''
    string should be a python format string with protocol, version, and
    operation keys.  For example: "/api/{protocol}/{version}/{api}"
    '''
    matchers = {
        "protocol": "(?P<protocol>[^/]+)",
        "version": "(?P<version>[^/]+)",
        "operation": "(?P<operation>[^/]+)"
    }
    return re.compile("^" + string.format(**matchers) + "/?$")


class Request(object):
    def __init__(self, environ):
        self.path = path(environ)
        self.body = body(environ)


class Response(object):
    import http.client
    HTTP_CODES = dict(
        (k, "{} {}".format(k, v)) for (k, v) in http.client.responses.items())

    def __init__(self):
        self.status = 200
        self.headers = {}
        self.body = ''
        self.charset = 'UTF-8'

    @property
    def headers_list(self):
        return [(str(h), str(v)) for (h, v) in self.headers.items()]

    @property
    def status_line(self):
        return Response.HTTP_CODES[self.status]


class WSGIApplication(object):
    UNKNOWN_OPERATION = RequestException(404, "Unknown Operation")

    def __init__(self, service, pattern):
        self.service = service
        self.pattern = build_pattern(pattern)

    def run(self, wsgi_server, **kwargs):
        wsgi_server.run(self, **kwargs)

    def abort(self, status, msg):
        raise RequestException(status, msg)

    def get_route_kwargs(self, path):
        r = self.pattern.search(path)
        if not r:
            raise self.UNKNOWN_OPERATION
        return r.groupdict()

    def __call__(self, environ, start_response):
        """WSGI-interface."""
        try:
            request = Request(environ)
            response = Response()

            kwargs = self.get_route_kwargs(request.path)
            kwargs["wire_in"] = request.body
            response.body = self.service(**kwargs)
        except RequestException as exception:
            logger.debug(
                "RequestException during WSGIApplication call",
                exc_info=exception)
            response.status = exception.status
            response.body = exception.body

        # Empty output
        if not response.body:
            response.headers['Content-Length'] = 0
            response.body = ''

        # Unicode strings
        if isinstance(response.body, str):
            response.body = response.body.encode(response.charset)

        # Byte strings
        if isinstance(response.body, bytes):
            response.headers['Content-Length'] = len(response.body)
            response.body = [response.body]

        start_response(response.status_line, response.headers_list)
        return response.body
