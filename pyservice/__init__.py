import json
import functools
import bottle

def parse_description(service, description):
    description = json.loads(description)
    return "Parsed"


class Service(object):
    def __init__(self, description):
        '''Load a service description to build against.'''
        self.description = parse_description(self, description)
        self._app = bottle.Bottle()

    @classmethod
    def from_file(cls, filename):
        '''Load description from file'''
        with open(filename) as f:
            return Service(f.read())

    def operation(self, name, **kwargs):
        '''Map an operation name to a function'''
        def wrapper(func):
            # Make sure operation hasn't already been mapped
            # TODO

            # Validate func args match description args exactly
            # TODO

            # Build bottle route
            route = {
                'prefix': "",
                'service': self.description.name,
                'operation': name
            }
            route = self._app.post("{prefix}/{service}/{operation}".format(**route))

            @functools.wraps(func)
            @route
            def wrapped_func():
                # Load request body,
                # Build func args from request body + service description defaults
                input = bottle.request.json
                input = self.build_input(name, input)

                # Invoke function
                output = func(*input)

                # Build return values,
                # Return output as json
                output = self.build_output(name, output)
                return json.dumps(output)

            return wrapped_func
        self._loaded_operations.append(name)
        return wrapper

    def build_input(self, name, input):
        pass

    def build_output(self, name, output):
        pass
