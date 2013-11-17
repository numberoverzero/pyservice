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

def test_base_layer_does_nothing():

    service, operation, noop = noop_service()
    pyservice.Layer(service)
    assert not pyservice.handle_request(service, operation, noop, {})


def test_stack_append_extend_pass_through():
    stack = pyservice.Stack()
    backing_list = stack.layers
    assert not backing_list

    stack.append("Hello")
    assert ["Hello"] == backing_list

    stack.extend(["World", "!"])
    assert ["Hello", "World", "!"] == backing_list

def test_layer_raise_exception():
    data = j('{"name": "ServiceName", "operations": [{"name":"Raise", "input": [], "output": []}]}')
    service = pyservice.parse_service(data)
    operation = service.operations["Raise"]


    class MyException(Exception):
        pass
    service._register_exception(MyException)

    class MyLayer(pyservice.Layer):
        def handle_request(self, context, next):
            next.handle_request(context)
            raise MyException("MyMessage")
    MyLayer(service)

    @service.operation("Raise")
    def func():
        return None

    result = pyservice.handle_request(service, operation, func, {})
    assert result == {
        "__exception": {
            "cls": "MyException",
            "args": ('MyMessage',)
        }
    }

def test_layer_raise_unknown_exception():

    # Same test as previous, but exception isn't registered.  Should get an Internal Error instead
    data = j('{"name": "ServiceName", "operations": [{"name":"Raise", "input": [], "output": []}]}')
    service = pyservice.parse_service(data)
    operation = service.operations["Raise"]


    class MyException(Exception): pass

    class MyLayer(pyservice.Layer):
        def handle_request(self, context, next):
            next.handle_request(context)
            raise MyException("MyMessage")
    MyLayer(service)

    @service.operation("Raise")
    def func():
        return None

    result = pyservice.handle_request(service, operation, func, {})
    assert result == {
        "__exception": {
            "cls": "ServerException",
            "args": ('Internal Error',)
        }
    }
