import os
import ujson

HERE = os.path.abspath(os.path.dirname(__file__))


def load_api(filename):
    '''
    Helper to load api specifications in the examples folder.

    Returns a nested dict appropriate for unpacking into Client or Service
    '''
    api_filename = os.path.join(HERE, filename)
    with open(api_filename) as api_file:
        api = ujson.loads(api_file.read())
    return api


def basic_wsgi(service):
    ''' Run a service with the reference wsgi implementation '''

    # wsgiref doesn't support TLS
    assert service.api["endpoint"]["scheme"] == "http"
    from wsgiref.simple_server import make_server

    host = service.api["endpoint"]["host"]
    port = service.api["endpoint"]["port"]
    httpd = make_server(host, port, service.wsgi_application)
    httpd.serve_forever()
