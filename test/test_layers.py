import json

import pyservice

j = json.loads

def noop_service():
    data = j('{"name": "ServiceName", "operations": [{"name":"noop", "input": [], "output": []}]}')
    service = pyservice.parse_service(data)
    operation = service.operations["noop"]
    @service.operation
    def noop():
        return None

    return service, operation, noop

def test_layer_ordering():

    class OrderingLayer(pyservice.Layer):
        def __init__(self, service, name, **kw):
            self.name = name
            expected_order.append(self.name)
            super(OrderingLayer, self).__init__(service, **kw)

        def handle_request(self, context, next):
            actual_order.append(self.name)
            next.handle_request(context)

    service, operation, noop = noop_service()
    expected_order = []
    actual_order = []
    OrderingLayer(service, "first")
    OrderingLayer(service, "second")

    assert not pyservice.handle_request(service, operation, noop, {})
    assert expected_order == actual_order


# test layer on_exception called

