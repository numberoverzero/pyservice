import re
import six

# Most names can only be \w*,
# with the special restriction that the
# first character must be a letter
NAME_RE = re.compile("^[a-zA-Z]\w*$")

def validate_name(name):
    if not NAME_RE.search(name):
        raise ValueError("Invalid name: '{}'".format(name))

def parse_name(data):
    name = data["name"]
    validate_name(name)
    return name

def parse_metadata(obj, data, blacklist):
    for key, value in six.iteritems(data):
        validate_name(key)
        if key not in blacklist:
            setattr(obj, key, value)

def to_list(signature, dict_):
    '''
    Convert dict -> list according to signature
    raises KeyError if data doesn't contain AT LEAST
    the fields required from signature
    '''
    # No output expected
    if not signature:
        return []

    # No validation needed - this will throw KeyError if a
    # required field is missing, and doesn't care about
    # extra fields
    return [dict_[key] for key in signature]

def to_dict(signature, *list_):
    '''
    Convert list_ -> dict according to signature
    raises KeyError if args doesn't contain the exact number of fields
    '''
    # No output expected
    if not signature:
        return {}

    # Special case single return value,
    # in case the return value is an iterable
    # (but represents one "thing")
    #if len(signature) == 1:
    #    key = signature[0]
    #    return {key: list_}

    if len(list_) != len(signature):
        raise ValueError("Output '{}' did not match signature '{}'".format(list_, signature))

    return dict(six.moves.zip(signature, list_))
