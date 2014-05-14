class ClientHandler(object):  # pragma: no cover
    '''
    Should handle 404, 500 and
    '''
    def register(self, service_name, operation, **kwargs):
        pass
    def handle(self, service_name, operation, request):
        pass


class RequestsHandler(ClientHandler):
    URI = "{schema}://{host}:{port}/{service}/{{operation}}"
    DEFAULT_OPTIONS = {
        "schema": "https",
        "host": "localhost",
        "port": "8080",
        "timeout": 5
    }

    def __init__(self, serializer, **kwargs):
        import requests
        self.serializer = serializer
        self.kwargs = dict(RequestsHandler.DEFAULT_OPTIONS)
        self.kwargs.update(kwargs)
        self.uris = {}

    def register(self, service_name, operation, **kwargs):
        kwargs = dict(self.kwargs)
        kwargs.update(kwargs)

        key = (service_name, operation)
        uri = RequestsHandler.URI.format(
            schema = kwargs["schema"],
            host = kwargs["host"],
            port = kwargs["port"],
            service = service_name,
            operation = operation
        )

        timeout = kwargs["timeout"]
        self.uris[key] = (uri, timeout)

    def handle(self, service_name, operation, request):  # pragma: no cover
        # Serialize request for wire
        wire_out = self.serializer.serialize({"request": request})

        # Load endpoint
        key = (service_name, operation)
        uri, timeout = self.uris[key]

        # Wire request
        wire_in = requests.post(uri, data=wire_out, timeout=timeout)

        # TODO: Handle 404/500 here
        #  response.raise_for_status()

        # Deserialize response from wire
        response = self.serializer.deserialize(wire_in.text)

        # Always provide response, __exception values
        return {
            "response": response.get("response", {}),
            "__exception": response.get("__exception", {})
        }
