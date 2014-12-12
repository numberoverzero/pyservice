"""
RequestContext stores state relevant to the current request, as well as
keeping track of the plugin execution order and providing a simple method
`advance` for calling the next plugin in the chain.
"""
import ujson
import collections


class Container(collections.defaultdict):
    DEFAULT_FACTORY = lambda: None

    def __init__(self):
        super().__init__(self, Container.DEFAULT_FACTORY)

    def __getattr__(self, name):
        return self[name]

    def __setattr__(self, name, value):
        self[name] = value


class Context(object):
    def __init__(self, service, operation, processor):
        self.service = service
        self.operation = operation
        self.processor = processor

    def process_request(self):
        self.processor.continue_execution()


class Processor(object):
    def __init__(self, service, operation, request_body):
        self.service = service
        self.operation = operation

        self.context = Context(service, operation, self)
        self.request = Container()
        self.request_body = request_body
        self.response = Container()
        self.response_body = None

        self.plugins = service.get_plugins(operation)

        self.index = -1
        self.state = "request"  # request -> operation -> function

    def execute(self):
        self.context.process_request()

    def continue_execution(self):
        self.index += 1
        plugins = self.plugins[self.state]
        n = len(plugins)

        if self.index > n:
            # Terminal point so that service.invoke
            # can safely call context.process_request()
            return
        elif self.index == n:
            if self.state == "request":
                self.index = -1
                self.state = "operation"

                self._deserialize_request()
                self.continue_execution()
                self._serialize_response()
            elif self.state == "operation":
                self.service.invoke(self.operation, self.request,
                                    self.response, self.context)
        # index < n
        else:
            if self.state == "request":
                plugins[self.index](self.context)
            elif self.state == "operation":
                plugins[self.index](self.request, self.response, self.context)

    def _deserialize_request(self):
        self.request.update(ujson.loads(self.request_body))

    def _serialize_response(self):
        self.response_body = ujson.dumps(self.response)
