import re
import json

NAME_RE = re.compile("^\w+$")


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


def load_fields(obj, data, translations=None):
    '''
    translations is an optional mapping from input key to output key
    ex.
        translations = { '__name' : 'name'}
    '''
    translations = translations or {}
    for key, value in data.items():
        key = translations.get(key, key)
        key = validate_key(key)
        if key in obj.fields:
            continue
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
        if isinstance(json_obj, str):
            json_obj = {"__name": json_obj}
        self.fields = set()
        self.reserved_fields = set()
        build_reserved_fields(self)
        load_fields(self, json_obj, {"__name": "name"})

    @classmethod
    def from_json(cls, data):
        return cls(dict(data))

    @classmethod
    def from_string(cls, string):
        data = json.loads(string.replace('\n', ''))
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
        for name, input in inputs.items():
            input["__name"] = input.get("__name", name)
            i[name] = Description(input)
        load_field(self, "input", i)

        o = {}
        outputs = default_field(json_obj, "output", dict)
        for name, output in outputs.items():
            output["__name"] = output.get("__name", name)
            o[name] = Description(output)
        load_field(self, "output", o)

        e = {}
        exceptions = default_field(json_obj, "exceptions", dict)
        for name, exception in exceptions.items():
            exception["__name"] = exception.get("__name", name)
            e[name] = Description(exception)
        load_field(self, "exceptions", e)


class ServiceDescription(Description):
    '''
    Define an API for clients and services.
    '''
    __reserved_fields__ = ["endpoint", "version", "operations"]

    def __init__(self, json_obj):
        super(ServiceDescription, self).__init__(json_obj)

        # Load endpoint and version from object
        # https://mysite.com/api/{protocol}/{version}/{operation}
        load_fields(self, json_obj, {
            "__name": "name",
            "__version": "version",
            "__endpoint": "endpoint"
        })

        os = {}
        operations = default_field(json_obj, "operations", dict)
        for name, operation in operations.items():
            operation["__name"] = operation.get("__name", name)
            os[name] = OperationDescription(operation)
        load_field(self, "operations", os)
