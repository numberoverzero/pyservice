import os
import json
import pytest
from pyservice import Service

#For loading relative files
here = os.path.dirname(os.path.realpath(__file__))

def test_bad_json():
    not_json = "bad_json"
    with pytest.raises(TypeError):
        Service.from_json(not_json)

def test_empty_service():
    junk_string = '{"name": "foo", "operations": []}'
    junk_json = json.loads(junk_string)
    my_service = Service.from_json(junk_json)
    assert len(my_service.operations) == 0

def test_from_filename():
    filename = os.path.join(here, "BeerService.json")
    my_service = Service.from_file(filename)
    assert len(my_service.operations) == 3
