"""
RequestContext stores state relevant to the current request, as well as
keeping track of the plugin execution order and providing a simple method
`advance` for calling the next plugin in the chain.
"""
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
    def __init__(self, service, operation):
        self.service = service
        self.operation = operation

    def execute(self):
        self.service.continue_execution(self)
