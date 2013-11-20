

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
        self.layers = layers or []
        self.index = 0

    def append(self, layer):
        self.layers.append(layer)

    def extend(self, iterable):
        self.layers.extend(iterable)

    def handle_request(self, context):
        # End of the chain
        if self.index >= len(self.layers):
            return
        layer = self.layers[self.index]
        self.index += 1
        layer.handle_request(context, self)
