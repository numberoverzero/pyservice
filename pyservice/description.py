import re
import six

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
