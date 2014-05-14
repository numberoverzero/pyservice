class ClientHandler(object):  # pragma: no cover
    def register(self, service, operation, client, **kwargs):
        '''operation and service are names, client is a Client obj'''
        pass
    def handle(self, service_name, operation, data, **kwargs):
        pass


class RequestsHandler(ClientHandler):
    uri = "{schema}://{host}:{port}/{service}/{{operation}}"
    default_options = {
        "schema": "https",
        "host": "localhost",
        "port": "8080",
        "timeout": 5
    }

    def __init__(self, **kwargs):
        self.kwargs = dict(RequestsHandler.default_options)
        self.kwargs.update(kwargs)
        self.uris = {}

    def register(self, service_name, operation, client, **kwargs):
        kwargs = dict(self.kwargs)
        kwargs.update(kwargs)

        key = (service_name, operation)
        uri = RequestsHandler.uri.format(
            schema = kwargs.get("schema", "https"),
            host = kwargs.get("host", "localhost"),
            port = kwargs.get("port", 8080),
            service = service_name,
            operation = operation
        )

        timeout = kwargs.get("timeout", 5)
        self.uris[key] = (uri, timeout)

    def handle(self, service_name, operation, data, **kwargs):  # pragma: no cover
        import requests
        key = (service_name, operation)
        uri, timeout = self.uris[key]
        response = requests.post(uri, data=data, timeout=timeout)
        response.raise_for_status()
        return response.text
