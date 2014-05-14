import re
import six
import json

# Most names can only be \w*,
# with the special restriction that the
# first character must be a letter
NAME_RE = re.compile("^[a-zA-Z]\w*$")


def validate_key(key):
    if not NAME_RE.search(key):
        raise ValueError("Invalid key: '{}'".format(key))
    return key

def default_field(obj, field, cls):
    '''
    If field isn't found in obj, instantiate a new cls and insert it into obj
    '''
    if field not in obj:
        obj[field] = cls()
    return obj[field]

def build_reserved_fields(obj):
    for cls in obj.__class__.__mro__:
        cls_rf = getattr(cls, '__reserved_fields__', [])
        obj.reserved_fields.update(cls_rf)

def load_field(obj, key, value):
    setattr(obj, key, value)
    obj.fields.add(key)

def load_fields(obj, data, whitelist=None):
    '''
    Any field included in whitelist will be inserted, even if that
    field is prohibited by the blacklist.
    '''
    whitelist = whitelist or []
    for key, value in six.iteritems(data):
        key = validate_key(key)
        if key in obj.fields:
            # Already set, don't do anything
            continue
        if key in whitelist or key not in obj.reserved_fields:
            load_field(obj, key, value)


class Description(object):
    '''
    Subclasses should include a `__reserved_field__` attribute which is added
    to all parent class' reserved_fields.  This combined list is the set of
    fields that are not loaded from the input object (by default - they can be
    forced to load from the object).
    '''
    __reserved_fields__ = ["name", "fields", "reserved_fields"]

    def __init__(self, json_obj, name=None):
        # Shortcut to build empty object out of a single string, a name
        if isinstance(json_obj, six.string_types):
            json_obj = { "name": json_obj }
        self.fields = set()
        self.reserved_fields = set()
        build_reserved_fields(self)
        load_fields(self, json_obj, ["name"])

    @classmethod
    def from_json(cls, data):
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


class OperationDescription(Description):
    '''
    Describes an operation's required input and output
    '''
    __reserved_fields__ = ["input", "output", "exceptions"]

    def __init__(self, json_obj):
        super(OperationDescription, self).__init__(json_obj)

        i = {}
        inputs = default_field(json_obj, "input", dict)
        for name, input in six.iteritems(inputs):
            if "name" not in input:
                i["name"] = name
            i[name] = Description(input)
        load_field(self, "input", i)

        o = {}
        outputs = default_field(json_obj, "output", dict)
        for name, output in six.iteritems(outputs):
            if "name" not in output:
                o["name"] = name
            o[name] = Description(output)
        load_field(self, "output", o)

        e = {}
        exceptions = default_field(json_obj, "exceptions", dict)
        for name, exception in six.iteritems(exceptions):
            if "name" not in exception:
                exception["name"] = name
            e[name] = Description(exception)
        load_field(self, "exceptions", e)


class ServiceDescription(Description):
    '''
    Define an API for clients and services.
    '''
    __reserved_fields__ = ["operations"]

    def __init__(self, json_obj):
        super(ServiceDescription, self).__init__(json_obj)

        os = {}
        operations = default_field(json_obj, "operations", dict)
        for name, operation in six.iteritems(operations):
            if "name" not in operation:
                operation["name"] = name
            os[name] = OperationDescription(operation)
        load_field(self, "operations", os)
