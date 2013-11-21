import json
import bottle
import pytest

from pyservice.serialize import JsonSerializer
from pyservice.handler import handle
from pyservice.service import parse_service

j = json.loads

def noop_service():
    data = j('{"name": "ServiceName", "operations": [{"name":"noop", "input": [], "output": []}]}')
    service = parse_service(data)
    operation = service.operations["noop"]
    @service.operation
    def noop():
        return None

    return service, operation, noop

def test_bad_deserialize():
    string = "{Malformed ] JSON"
    serializer = JsonSerializer()

    with pytest.raises(ValueError):
        serializer.deserialize(string)

def test_good_deserialize():
    string = '{"good": ["json"]}'
    serializer = JsonSerializer()
    serializer.deserialize(string)

def test_bad_serialize():
    # json can't serialize types
    data = {"bad": type}
    serializer = JsonSerializer()

    with pytest.raises(TypeError):
        serializer.serialize(data)

def test_good_serialize():
    data = {"good": ["json"]}
    expected = '{"good": ["json"]}'

    serializer = JsonSerializer()
    actual = serializer.serialize(data)

    assert expected == actual

def test_bad_serializer():
    # When serialize throws, handle should raise a Bottle 500
    class BadJsonSerializer(object):
        format = "json"
        content_type = "application/json"

        def serialize(self, data, **kw):
            raise Exception("Serialize failed!")
            return json.dumps(data)

        def deserialize(self, string, **kw):
            return json.loads(string)

    service, operation, noop = noop_service()
    with pytest.raises(bottle.BottleException):
        handle(service, operation, "{}", BadJsonSerializer())
