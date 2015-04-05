from examples import load_api
import pyservice

service = pyservice.Service(**load_api('echo/api.json'))


@service.operation("greet")
def greet(request, response, context):
    name = request.name
    city = request.city
    if not name:
        raise service.exceptions.InvalidName("Surely you have a name!")
    if not city:
        raise service.exceptions.InvalidCity(
            "Please tell me where you're from.")
    response.greeting = "Hello, {}!".format(name)
    response.question = "How's the weather in {}?".format(city)


@service.operation("echo")
def echo(request, response, context):
    response.value = request.value


# Let's add a plugin for auth.  This is an "operation" scope because we need
# access to the operation parameters.  The "request" scope is for pre/post
# plugins, that need to ensure the request has been serialized before they
# close (such as sqlalchemy)

# For now we'll only authenticate calls to the `echo` operation, with a set of
# super secret credentials
expected_user = "admin"
expected_password = "hunter2"
auth_required = ["echo"]


@service.plugin(scope="operation")
def auth_n(request, response, context):
    user, password = request.user, request.password
    credentials_match = user == expected_user and password == expected_password
    requires_auth = context.operation in auth_required

    if credentials_match or not requires_auth:
        context.process_request()
    else:
        raise service.exceptions.Unauthorized("Invalid credentials.")


def main():
    # using http because wsgiref doesn't support TLS
    from wsgiref.simple_server import make_server

    host = service.api["endpoint"]["host"]
    port = service.api["endpoint"]["port"]
    httpd = make_server(host, port, service.wsgi_application)
    httpd.serve_forever()

if __name__ == "__main__":
    main()
