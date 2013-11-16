import pytest
import pyservice

def build_context(input_json=None, output_json=None, func=None, input=None, output=None):
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
        "output": output_json
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
    pyservice.validate_input(context)
    assert dict(context["input"]) == dict(input_json)

def test_on_input_without_wrapping():
    input_json = {
        "b": "World",
        "c": "!",
        "a": "Hello"
    }

    input = "abc"

    context = build_context(input_json=input_json, input=input)
    with pytest.raises(pyservice.ServerException):
        pyservice.validate_input(context)

def test_on_input_no_args():
    input_json = {}

    def func():
        None

    input = None

    context = build_context(input_json=input_json, func=func, input=input)
    pyservice.validate_input(context)
    assert dict(context["input"]) == dict(input_json)

def test_on_input_too_few_args():
    input_json = {
        "a": "Hello"
    }

    def func(a, b):
        None

    input = "ab"

    context = build_context(input_json=input_json, func=func, input=input)
    with pytest.raises(pyservice.ClientException):
        pyservice.validate_input(context)

def test_on_input_too_many_args():
    input_json = {
        "a": "Hello",
        "b": "World"
    }

    def func(a):
        None

    input = "a"

    context = build_context(input_json=input_json, func=func, input=input)
    pyservice.validate_input(context)


def test_on_input_wrong_args():
    input_json = {
        "wrong": "Hello",
        "args": "World"
    }

    def func(a, b):
        None

    input = "ab"

    context = build_context(input_json=input_json, func=func, input=input)
    with pytest.raises(pyservice.ClientException):
        pyservice.validate_input(context)

def test_on_output_no_args():
    output_json = {}

    def func():
        None

    output = None

    context = build_context(output_json=output_json, func=func, output=output)
    pyservice.validate_output(context)
    assert not context["output"]

def test_on_output_too_few_args():
    output_json = {"a": ["Hello"]}

    def func():
        None

    output = "ab"

    context = build_context(output_json=output_json, func=func, output=output)
    with pytest.raises(pyservice.ServerException):
        pyservice.validate_output(context)

def test_on_output_too_many_args():
    output_json = {
        "a": "Hello",
        "b": "World",
        "c": "!"
    }

    def func():
        None

    output = "ab"

    context = build_context(output_json=output_json, func=func, output=output)
    pyservice.validate_output(context)

def test_on_output_single_string():
    output_json = {"a": "Hello"}

    def func():
        None

    output = "a"

    context = build_context(output_json=output_json, func=func, output=output)
    pyservice.validate_output(context)
    assert context["output"] == {"a": "Hello"}
