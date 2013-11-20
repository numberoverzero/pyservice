import pytest

from pyservice.serialize import JsonSerializer

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
