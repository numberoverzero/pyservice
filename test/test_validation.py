import pytest
import pyservice

def build_context(input_json=None, result=None, func=None, input=None, output=None):
    service_json = {
        "name": "service_name",
        "operations": [{
            "name": "func",
            "input": list(input) if input else [],
            "output": list(output) if output else []
        }]
    }
    service = pyservice.Service.from_json(service_json)
    operation = service.operations["func"]
    if func:
        service.operation(func)

    context = {
        "service": service,
        "operation": operation,
        "input": input_json,
        "output": {},
        "result": result
    }
    return context

def test_on_input_same_args():
    input_json = {
        "b": "World",
        "c": "!",
        "a": "Hello"
    }

    def func(a, b, c):
        return None

    input = "abc"

    context = build_context(input_json=input_json, func=func, input=input)
    layer = pyservice.BasicValidationLayer()
    layer.on_input(context)
    assert dict(context["input"]) == dict(input_json)

def test_on_input_without_wrapping():
    input_json = {
        "b": "World",
        "c": "!",
        "a": "Hello"
    }

    input = "abc"

    context = build_context(input_json=input_json, input=input)
    layer = pyservice.BasicValidationLayer()
    with pytest.raises(pyservice.ServerException):
        layer.on_input(context)

def test_on_input_no_args():
    input_json = {}

    def func():
        None

    input = None

    context = build_context(input_json=input_json, func=func, input=input)
    layer = pyservice.BasicValidationLayer()
    layer.on_input(context)
    assert dict(context["input"]) == dict(input_json)

def test_on_input_too_few_args():
    input_json = {
        "a": "Hello"
    }

    def func(a, b):
        None

    input = "ab"

    context = build_context(input_json=input_json, func=func, input=input)
    layer = pyservice.BasicValidationLayer()
    with pytest.raises(pyservice.ClientException):
        layer.on_input(context)

def test_on_input_too_many_args():
    input_json = {
        "a": "Hello",
        "b": "World"
    }

    def func(a):
        None

    input = "a"

    context = build_context(input_json=input_json, func=func, input=input)
    layer = pyservice.BasicValidationLayer()
    with pytest.raises(pyservice.ClientException):
        layer.on_input(context)

def test_on_input_wrong_args():
    input_json = {
        "wrong": "Hello",
        "args": "World"
    }

    def func(a, b):
        None

    input = "ab"

    context = build_context(input_json=input_json, func=func, input=input)
    layer = pyservice.BasicValidationLayer()
    with pytest.raises(pyservice.ClientException):
        layer.on_input(context)

def test_on_output_no_args():
    result = None

    def func():
        None

    output = None

    context = build_context(result=result, func=func, output=output)
    layer = pyservice.BasicValidationLayer()
    layer.on_output(context)
    assert not context["output"]

def test_on_output_too_few_args():
    result = ["Hello"]

    def func():
        None

    output = "ab"

    context = build_context(result=result, func=func, output=output)
    layer = pyservice.BasicValidationLayer()
    with pytest.raises(pyservice.ServerException):
        layer.on_output(context)

def test_on_output_too_many_args():
    result = [
        "Hello",
        "World",
        "!"
    ]

    def func():
        None

    output = "ab"

    context = build_context(result=result, func=func, output=output)
    layer = pyservice.BasicValidationLayer()
    with pytest.raises(pyservice.ServerException):
        layer.on_output(context)

def test_on_output_wrong_args():
    result = [
        "Hello",
        "World"
    ]

    def func():
        None

    output = None

    context = build_context(result=result, func=func, output=output)
    layer = pyservice.BasicValidationLayer()
    with pytest.raises(pyservice.ServerException):
        layer.on_output(context)

def test_on_output_single_string():
    result = "Hello"

    def func():
        None

    output = "a"

    context = build_context(result=result, func=func, output=output)
    layer = pyservice.BasicValidationLayer()
    layer.on_output(context)
    assert context["output"] == {"a": "Hello"}
