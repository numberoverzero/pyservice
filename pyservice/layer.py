

class Layer(object):
    def __init__(self, service=None, **kwargs):
        if service:
            service._register_layer(self)

    def handle_request(self, context, next):
        # Do some pre-request work

        # Have the next layer process the request
        next.handle_request(context)

        # Do some post-request work


class Stack(object):
    def __init__(self, layers=None):
        self.__layers = layers or []
        self.__index = 0

    def handle_request(self, context):
        # End of the chain
        if self.__index >= len(self.__layers):
            return
        layer = self.__layers[self.__index]
        self.__index += 1
        layer.handle_request(context, self)
