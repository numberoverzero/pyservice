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

        # If exceptions, operations, or operation in/out
        # are missing, fill them in with empty lists
        def default_list(obj, field):
            if field not in obj:
                obj[field] = []
            return obj[field]
        default_list(self.__obj, "exceptions")
        ops = default_list(self.__obj, "operations")
        for op in ops:
            default_list(op, "input")
            default_list(op, "output")

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
        obj_operations = self.__obj["operations"]
        return [op["name"] for op in obj_operations]

    @cached_property
    def exceptions(self):
        return self.__obj["exceptions"]

    @cached
    def operation(self, op_name):
        if op_name not in self.operations:
            raise KeyError("Unknown operation '{}'".format(op_name))
        operations_obj = self.__obj["operations"]
        for operation_obj in operations_obj:
            if operation_obj["name"] == op_name:
                return operation_obj

    @cached_property
    def metadata(self):
        blacklist = ["name", "operations", "exceptions"]
        return parse_metadata(self.__obj, blacklist)

    def validate(self):
        validate_name(self.name)

        op_names = self.operations
        if len(set(op_names)) != len(op_names):
            raise KeyError("Duplicate operations found: '{}'".format(op_names))
        for op_name in op_names:
            validate_name(op_name)
            operation = self.operation(op_name)
            for attr in ["input", "output"]:
                for field in operation[attr]:
                    validate_name(field)

        for exception in self.exceptions:
            validate_name(exception)

        # Accessing properties for side-effects :(
        self.metadata
