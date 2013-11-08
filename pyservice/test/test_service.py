import os
from pyservice import Service
#For loading relative files
here = os.path.dirname(os.path.realpath(__file__))


def test_from_string():
    junk_string = "{}"
    my_service = Service(junk_string)
    assert my_service.description == "Parsed"

def test_from_filename():
    filename = os.path.join(here, "BeerService.json")
    my_service = Service.from_file(filename)
    assert my_service.description == "Parsed"
