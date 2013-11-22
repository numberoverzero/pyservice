import json
import requests

from pyservice.service import parse_service
from pyservice.common import (
    ClientException,
    ServiceException
)

from pyservice import utils


class Client(object):
    def __init__(self, service, **config):
        self._service = service
        self._config = config

        # Get schema/host/port from service
        # Fallback to config
        # Default to http://localhost:8080
        schema = getattr(service, "schema", None)
        schema = schema or config.get("schema", None)
        schema = schema or "http"

        host = getattr(service, "host", None)
        host = host or config.get("host", None)
        host = host or "localhost"

        port = getattr(service, "port", None)
        port = port or config.get("port", None)
        port = port or 8080

        uri = {
            "schema": schema,
            "host": host,
            "port": port,
            "service": service.name
        }
        self._uri = "{schema}://{host}:{port}/{service}/{{operation}}".format(**uri)
        map(self._build_operation, self._service.operations)

    @classmethod
    def from_json(cls, data, **config):
        service = parse_service(data)
        return Client(service, **config)

    @classmethod
    def from_file(cls, filename, **config):
        with open(filename) as f:
            data = json.loads(f.read())
            return Client.from_json(data, **config)

    def _call_operation(self, operation, *args):
        uri = self._uri.format(operation=operation)

        signature = self._service.operations[operation].input
        dict_ = utils.to_dict(signature, *args)
        headers = {'Content-type': 'application/json'}

        response = requests.post(uri, data=json.dumps(dict_), headers=headers)
        response = response.json()

        # Handle exception
        self._check_exception(response)

        signature = self._service.operations[operation].output
        result = utils.to_list(signature, response)

        if not signature:
            return None
        if len(signature) == 1:
            return result[0]
        return result

    def _check_exception(self, response):
        if len(response) == 1:
            if "__exception" in response:
                exception = response["__exception"]
                self._throw_exception(exception["cls"], *exception["args"])

    def _throw_exception(self, exception, *args):
        ex_type = exception.encode('ascii', 'ignore')
        raise type(ex_type, (ServiceException,), {})(*args)

    def _build_operation(self, operation):
        setattr(self, operation,
            lambda *args: self._call_operation(operation, *args))
