docstring_Client="""# Local endpoint for a service

# =================
# Operations
# =================

client = Client(some_description, handler, serializer)

# Make function calls through the operation directly:

input_value = "Hello, World"
output_value = client.echo(value=input_value)
assert input_value == output_value

# Or through client.operations:

input_value = "Hello, World"
output_value = client.operations["echo"](value=input_value)
assert input_value == output_value

# Or use the shorthand `client.op`

client.op["complex_call"](context="Really Complex Object", param='foo')


# =================
# Exceptions
# =================
# Client functions throw real exceptions,
# which are namespaced under client.exceptions. (shorthand `client.ex`)

value = 'not a number'
try:
    client.op['only_takes_numbers'](value=value)
except client.exceptions.InvalidNumber e:
    print("'{}' is not a number!".format(value))
    raise e

try:
    client.sqrt(value=-12)
except client.ex.InvalidNumber e:
    print("WARN: Failed to get square root")
    raise e

# =================
# Extensions
# =================
# See the readme section on client/service extensions."""

docstring_Service="""
# Remote endpoint for a service

# =================
# Operations
# =================
# Operations are defined in the service's Description,
# and should be mapped to a function with the same input
# using the Serivice.operation decorator

description = ServiceDescription({
    "name": "some_service",
    "operations": {
        "echo": {
            "input": {
                "value1": {},
                "value2": {}
            },
            "output": {
                "result1": {},
                "result2": {}
            }
        }
    }
})
service = Service(description)

@service.operation("echo")
def echo_func(value1, value2):
    return value1, value2

# =================
# Exceptions
# =================
# Exceptions thrown are sent back to the client and raised
# When not debugging, only whitelisted (included in
# service description) exceptions are thrown -
# all other exceptions are returned as a generic
# ServiceException.
# Like the Client, exceptions can be referenced
# through the service itself.  Both of the following
# are valid:
#     raise service.exceptions.InvalidId
#     raise InvalidId
#
# Note that this means exceptions are verified by NAME ONLY, although
# this can be adjusted by overriding handle_exception

description = ServiceDescription({
    "name": "tasker",
    "operations": {
        {
            "name": "get_task",
            "input": {
                "task_id": {}
            },
            "output": {
                "name": {},
                "description": {}
            },
            "exceptions": {
                "KeyError": {},
                "InvalidId": {}
            }
        }
    }
})
service = Service(description)
tasks = {}

@service.operation("get_task")
def operation(task_id):
    if not valid_format(task_id):
        raise InvalidId(task_id)
    return tasks[task_id]  # Can raise KeyError

# =================
# Extensions
# =================
# See the readme section on client/service extensions.
"""

docstring_extension="""#Creates an Extension that only overrides the
# handle_operation function.  use the 'yield' keyword to indicate where the rest
# of the operation handler chain should be invoked.  Optionally yield an
# (operation, context) tuple or use a raw `yield` to pass the input operation
# and context.

# Similar in usage to the @contextmanager decorator

# Typical usage:

@extension
def Logger(operation, context):
    # Before the rest of the handlers execute
    start_time = time.now()

    #Process the operation
    yield

    # Log the operation timing
    end_time = time.now()

    msg = "Operation {} completed in {} seconds."
    name = context["operation"].name
    logger.info(msg.format(name, end_time - start_time))

service = Service(some_description)
logger = Logger(service)

# The rest of the handlers in a chain are executed when control is yielded.
#To return a different operation and context:

@extension
def ProtectVirus(operation, context):
    if operation == "delete_object":
        filename = context["input"]["filename"]
        # Don't delete the virus, give wrong filename
        if filename == virus_filename:
            fake_context = dict(context)
            fake_context["input"]["filename"] = filename[1:]
            yield operation, fake_context
        else:
            # Not deleting the infected file
            yield
    else:
        # Not deleteing anything
        yield

# You probably shouldn't use this extension.
"""

docs = {
    'Client': docstring_Client,
    'Service': docstring_Service,
    'extension': docstring_extension
}

def docstring(obj):
    obj.__doc__ = docs.get(obj.__name__, obj.__doc__)
    return obj
