import json


def default_field(obj, field, cls):
    '''
    If field isn't found in obj, instantiate a new cls and insert it into obj
    '''
    if field not in obj:
        obj[field] = cls()
    return obj[field]


def load_fields(obj, data, translations=None):
    '''
    translations is an optional mapping from input key to output key
    ex.
        translations = { '__name' : 'name'}
    '''
    translations = translations or {}
    for key, value in data.items():
        key = translations.get(key, key)
        setattr(obj, key, value)


class Description(object):
    def __init__(self, json_obj, name=None):
        # Shortcut to build empty object out of a single string, a name
        if isinstance(json_obj, str):
            json_obj = {"name": json_obj}
        load_fields(self, json_obj)

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
    def __init__(self, json_obj):
        super(OperationDescription, self).__init__(json_obj)

        self.input = {}
        inputs = default_field(json_obj, "input", dict)
        for name, input in inputs.items():
            input["name"] = input.get("name", name)
            self.input[name] = Description(input)

        self.output = {}
        outputs = default_field(json_obj, "output", dict)
        for name, output in outputs.items():
            output["name"] = output.get("name", name)
            self.output[name] = Description(output)

        self.exceptions = {}
        exceptions = default_field(json_obj, "exceptions", dict)
        for name, exception in exceptions.items():
            exception["name"] = exception.get("name", name)
            self.exceptions[name] = Description(exception)


class ServiceDescription(Description):
    '''
    Define an API for clients and services.
    '''
    def __init__(self, json_obj):
        super(ServiceDescription, self).__init__(json_obj)

        self.operations = {}
        operations = default_field(json_obj, "operations", dict)
        for name, operation in operations.items():
            operation["name"] = operation.get("name", name)
            self.operations[name] = OperationDescription(operation)
