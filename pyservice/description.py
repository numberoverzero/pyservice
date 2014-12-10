import ujson


def build_field(obj, field, cls):
    d = {}
    if field not in obj:
        obj[field] = dict()
    for name, value in obj[field].items():
        value["name"] = value.get("name", name)
        d[name] = cls(value)
    return d


class Description(object):
    def __init__(self, json_obj, name=None):
        # Shortcut to build empty object out of a single string, a name
        if isinstance(json_obj, str):
            json_obj = {"name": json_obj}
        for key, value in json_obj.items():
            setattr(self, key, value)

    @classmethod
    def from_json(cls, data):
        return cls(dict(data))

    @classmethod
    def from_string(cls, string):
        data = ujson.loads(string.replace('\n', ''))
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
        for field in ["input", "output", "exceptions"]:
            setattr(self, field, build_field(json_obj, field, Description))


class ServiceDescription(Description):
    '''
    Define an API for clients and services.
    '''
    def __init__(self, json_obj):
        super(ServiceDescription, self).__init__(json_obj)
        self.operations = build_field(
            json_obj, "operations", OperationDescription)
