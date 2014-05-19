import json

"""
Add your own serializers, and key off format

from pyservice.serialize import serializers

dict = serializers[format]['deserialize'](string)
string = serializers[format]['serialize'](dict)

"""


class JsonSerializer(object):
    def serialize(self, data):
        return json.dumps(data)

    def deserialize(self, string):
        return json.loads(string)


serializers = {
    'json': JsonSerializer()
}
