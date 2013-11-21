import re
import six
from pyservice.common import ServiceException

# Most names can only be \w*,
# with the special restriction that the
# first character must be a letter
NAME_RE = re.compile("^[a-zA-Z]\w*$")

def validate_name(name):
    if not NAME_RE.search(name):
        raise ValueError("Invalid name: '{}'".format(name))

def validate_input(context):
    '''Make sure input has at least the required fields for mapping to a function'''
    json_input = set(context["input"])
    op_args = set(context["operation"].input)
    if not json_input.issuperset(op_args):
        msg = 'Input "{}" does not contain required params "{}"'
        raise ServiceException(msg.format(context["input"], op_args))
    if context["operation"]._func is None:
        raise ServiceException("No wrapped function to order input args by!")

def validate_output(context):
    '''Make sure the expected fields are present in the output'''
    json_output = set(context["output"])
    op_returns = set(context["operation"].output)
    if not json_output.issuperset(op_returns):
        msg = 'Output "{}" does not contain required values "{}"'
        raise ServiceException(msg.format(context["output"], op_returns))

def validate_exception(context):
    '''Make sure the exception returned is whitelisted - otherwise throw a generic InteralException'''
    exception = context["exception"]
    service = context["service"]

    whitelisted = exception.__class__ in service.exceptions
    debugging = service._debug

    if not whitelisted and not debugging:
        # Blow away the exception
        context["exception"] = ServiceException()

def parse_name(data):
    name = data["name"]
    validate_name(name)
    return name

def parse_metadata(obj, data, blacklist):
    for key, value in six.iteritems(data):
        validate_name(key)
        if key not in blacklist:
            setattr(obj, key, value)
