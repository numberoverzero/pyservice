import re
import six
import json
from pyservice.util import cached, cached_property

# Most names can only be \w*,
# with the special restriction that the
# first character must be a letter
NAME_RE = re.compile("^[a-zA-Z]\w*$")

def validate_name(name):
    if not NAME_RE.search(name):
        raise ValueError("Invalid name: '{}'".format(name))

def parse_metadata(data, blacklist=None):
    metadata = {}
    blacklist = blacklist or []
    for key, value in six.iteritems(data):
        validate_name(key)
        if key not in blacklist:
            metadata[key] = value
    return metadata

class Description(object):
    '''
    Read-only.  Properties are cached.

    Wrapper around a json-like object
      which provides helpers for inspecting
      expected attributes, such as input,
      output, and operations.
    '''
    def __init__(self, json_obj):
        self.__obj = dict(json_obj)

    @classmethod
    def from_json(self, data):
        return Description(data)

    @classmethod
    def from_string(self, string):
        data = json.loads(string.replace('\n',''))
        return Description.from_json(data)

    @classmethod
    def from_file(self, filename):
        with open(filename) as file_obj:
            string = file_obj.read()
            return Description.from_string(string)

    @cached_property
    def name(self):
        return self.__obj["name"]

    @cached_property
    def operations(self):
        obj_operations = self.__obj.get("operations", [])
        return [op["name"] for op in obj_operations]

    @cached_property
    def exceptions(self):
        return self.__obj.get("exceptions", [])
