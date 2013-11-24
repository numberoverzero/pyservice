import six
import json

"""Service layers expects the request/response context to be one
dictionary - the pyservice framework makes extensive use of this format,
and the layer interface is exclusively context-based.  This is great
for JSON-like wire formats, but more work for others.

For other formats, an adapter can be created which translates between
the wire format and dictionary objects.  The return does not need to be
a python dict - anything that supports the full dictionary interface
works.

Communication looks something like:

----------
| Client |
----------
    V
    |----- (list) function call: client.operation(*args)
    |
    |----- (dict) pyservice.Client translates args into dictionary,
    |               according to operation's input signature
    V               This MUST use a strict match - extra/missing fields raise exceptions
    |
    |----- (dict) Every layer of the client stack gets a chance to manipulate
    |               the input dict on its way out
    |
    |----- (wire) The client serializer converts the dictionary into a wire
    |               format.  If serialization is strict, the serialized format must
    V               contain the exact operation signature's input fields.
    |               Otherwise, an exception is raised
    |
    | === INTERNET MAGIC HERE ===
    |
    |----- (dict) The server serializer converts the wire format into a
    |               dictionary-like object.  If strict, the deserialized object must
    V               contain the exact operation signature's input fields.
    |               Otherwise, an exception is raised
    |
    |----- (dict) Every layer of the server stack gets a chance to manipulate
    |               the input dict on its way in
    |
    |----- (list) pyservice.Server translates the dictionary into args,
    |               according to operation's input signature
    V               This MAY use a strict match - if strict,
    |               extra/missing fields raise exceptions
    |
    |----- (list) function call: operation._wrapped_func(*args)
    V
----------
| Server |
----------

RETURN TRIP
    The server -> Client response is identical to above, with the Server and Client in opposite positions, and
    the work "output" replacing the word "input".  Pay extra attention to where strict MUST/MAY be used on the
    return trip: MUST from (Server's wrapped func -> dict), MAY from (Client's dict -> list)

NOTE
    A special case occurs when the input/output signature has exactly one element:
        Strict checking always passes, even when the value is None or an Array.
        To prevent None from being a valid single-field input/output,
        create a custom serializer which raises on those conditions.  This can
        of course also be used to prevent Nones from passing any field.
"""


class JsonSerializer(object):
    format = "json"
    content_type = "application/json"

    def serialize(self, data, **kw):
        return json.dumps(data)

    def deserialize(self, string, **kw):
        return json.loads(string)

def to_list(signature, data):
    '''
    Convert data -> list according to signature
    raises KeyError if data doesn't contain AT LEAST
        the fields required from signature

    signature must be a list.
    data must be a dict-like object
    '''
    # No validation needed - raises KeyError if a
    #     required field is missing
    return [data[key] for key in signature]

def to_dict(signature, data):
    '''
    Convert data -> dict according to signature
    raises KeyError if data doesn't contain the EXACT number of fields

    signature must be a list.
    data must be iterable.
    '''
    if not signature:
        return {}
    if len(data) != len(signature):
        raise ValueError("Value '{}' did not match signature '{}'".format(data, signature))

    return dict(six.moves.zip(signature, data))
