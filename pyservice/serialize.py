import json
import logging
logger = logging.getLogger(__name__)

"""
Add your own serializers, and key off format

from pyservice.serialize import serializers

dict = serializers[format]['deserialize'](string)
string = serializers[format]['serialize'](dict)

"""


class JsonSerializer(object):
    def serialize(self, data, *, debug=False):
        if debug:
            logger.debug("serialize {}".format(data))
        return json.dumps(data)

    def deserialize(self, string):
        if debug:
            logger.debug("deserialize {}".format(string))
        return json.loads(string)


serializers = {
    'json': JsonSerializer()
}
