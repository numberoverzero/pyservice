import json
import requests

from pyservice.service import parse_service
from pyservice.common import (
    ClientException,
    ServiceException
)


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
        data = self._pack_params(operation, *args)
        headers = {'Content-type': 'application/json'}

        response = requests.post(uri, data=json.dumps(data), headers=headers)
        result = self._unpack_result(operation, response.json())
        return result

    def _pack_params(self, operation, *args):
        # Verify args match function signature
        func_args = self._service.operations[operation].input
        if args and not func_args:
            raise ClientException("Passed args '{}' but not expecting any".format(args))
        return dict(zip(func_args, args))

    def _unpack_result(self, operation, response):
        func_results = self._service.operations[operation].output
        if len(response) == 1:
            if "__exception" in response:
                exception = response["__exception"]
                self._throw_exception(exception["cls"], *exception["args"])
            return response[func_results[0]]
        if len(func_results) != len(response):
            raise ServiceException("Expected {} results, got {}".format(len(response), len(func_results)))
        if not func_results:
            return None
        return [response[key] for key in func_results]

    def _throw_exception(self, exception, *args):
        ex_type = exception.encode('ascii', 'ignore')
        raise type(ex_type, (ServiceException,), {})(*args)

    def _build_operation(self, operation):
        setattr(self, operation,
            lambda *args: self._call_operation(operation, *args))
