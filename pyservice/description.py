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
    return name

def parse_metadata(data, blacklist=None):
    metadata = {}
    blacklist = blacklist or []
    for key, value in six.iteritems(data):
        validate_name(key)
        if key not in blacklist:
            metadata[key] = value
    return metadata

def default_field(obj, field, cls):
    if field not in obj:
        obj[field] = cls()
    return obj[field]


class Description(object):
    reserved_fields = ["name"]

    def __init__(self, json_obj):
        if isinstance(json_obj, six.string_types):
            json_obj = {
                "name": json_obj
            }
        self._obj = json_obj
        validate_name(self.name)

    @classmethod
    def from_json(cls, data):
        # Copy input
        return cls(dict(data))

    @classmethod
    def from_string(cls, string):
        data = json.loads(string.replace('\n',''))
        return cls.from_json(data)

    @classmethod
    def from_file(cls, filename):
        with open(filename) as file_obj:
            string = file_obj.read()
            return cls.from_string(string)

    @cached_property
    def name(self):
        return self._obj["name"]

    @cached_property
    def metadata(self):
        blacklist = self._reserved_fields()
        return parse_metadata(self._obj, blacklist)

    def _reserved_fields(self):
        reserved_fields = []
        # Walk in reverse to preserve order
        mro = reversed(self.__class__.__mro__)
        for cls in mro:
            cls_rf = getattr(cls, 'reserved_fields', [])
            reserved_fields.extend(cls_rf)
        return reserved_fields




class OperationDescription(Description):
    reserved_fields = ["input", "output"]

    def __init__(self, json_obj):
        super(OperationDescription, self).__init__(json_obj)

        # Input/Output are basic Descriptions because they
        # have no attributes besides their name
        ins = default_field(self._obj, "input", list)
        in_objs = [Description(in_) for in_ in ins]
        # List, not dict, since order matters
        self._obj["input"] = in_objs

        outs = default_field(self._obj, "output", list)
        out_objs = [Description(out_) for out_ in outs]
        # List, not dict, since order matters
        self._obj["output"] = out_objs

    @cached_property
    def input(self):
        return self._obj["input"]

    @cached_property
    def output(self):
        return self._obj["output"]


class ServiceDescription(Description):
    reserved_fields = ["exceptions", "operations"]

    '''
    Read-only.  Properties are cached.

    Wrapper around a json-like object
      which provides helpers for inspecting
      expected attributes, such as input,
      output, and operations.
    '''
    def __init__(self, json_obj):
        super(ServiceDescription, self).__init__(json_obj)

        # Exceptions are basic Descriptions because they have no attributes
        # right now besides their name
        exs = default_field(self._obj, "exceptions", list)
        ex_objs = [Description(ex) for ex in exs]
        self._obj["exceptions"] = dict((ex.name, ex) for ex in ex_objs)

        ops = default_field(self._obj, "operations", list)
        op_objs = [OperationDescription(op) for op in ops]
        self._obj["operations"] = dict((op.name, op) for op in op_objs)

        self.metadata

        # Convert to dict so the following are both possible:
        # "foo_operation" in desc.operations
        # if "field" in desc.operations["foo_operation"].input

        # TODO: An operation that isn't an object (just a string) should be valid-
        #           it has no onput or output
        #       Add test for above
        #       Same is true of exceptions - if they're just a string, that is the name attribute
        #       Add test for operation object without name field
        # Basically, the following are equivalent:
        #
        # {
        #   "operations": [
        #       {"name": "operation_name"}
        #   ]
        # }

        # {
        #   "operations": [
        #       "operation_name"
        #   ]
        # }

    @cached_property
    def operations(self):
        return self._obj["operations"]

    @cached_property
    def exceptions(self):
        return self._obj["exceptions"]
