class ClientHandler(object):  # pragma: no cover
    def register(self, service, operation, client, **kwargs):
        '''operation and service are names, client is a Client obj'''
        pass
    def handle(self, service, operation, data, **kwargs):
        pass


class RequestsHandler(ClientHandler):
    uri = "{schema}://{host}:{port}/{service}/{{operation}}"
    def __init__(self, **kwargs):
        self.kwargs = kwargs or {}
        self.uris = {}

    def register(self, service, operation, client, **kwargs):
        uri_data = dict(self.kwargs)
        uri_data.update(kwargs)

        key = (service, operation)
        uri = RequestsHandler.uri.format(
            schema = uri_data.get("schema", "http"),
            host = uri_data.get("host", "localhost"),
            port = uri_data.get("port", 8080),
            service = service,
            operation = operation
        )

        timeout = uri_data.get("timeout", 5)
        self.uris[key] = (uri, timeout)

    def handle(self, service, operation, data, **kwargs):  # pragma: no cover
        import requests
        key = (service, operation)
        uri, timeout = self.uris[key]
        response = requests.post(uri, data=data, timeout=timeout)
        response.raise_for_status()
        return response.text