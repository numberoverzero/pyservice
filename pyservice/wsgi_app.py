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


class Response(object):
    import http.client
    HTTP_CODES = dict(
        (k, "{} {}".format(k, v)) for (k, v) in http.client.responses.items())
    INTERNAL_ERROR = RequestException(500, "Internal Error")

    def __init__(self):
        self.status = 200
        self.headers = {}
        self.charset = 'UTF-8'
        self.body = ''

    @property
    def body(self):
        '''Body as string'''
        return self._body[0].decode(self.charset)

    @body.setter
    def body(self, value):
        '''Must be a unicode string'''

        if not isinstance(value, str):
            raise Response.INTERNAL_ERROR

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
            response = Response()
            kwargs = self.get_route_kwargs(path(environ))
            kwargs["wire_in"] = body(environ)
            response.body = self.service(**kwargs)
        except RequestException as exception:
            logger.debug(
                "RequestException during WSGIApplication call",
                exc_info=exception)
            response.status = exception.status
            response.body = exception.msg

        start_response(response.status_line, response.headers_list)
        return response.body_raw
