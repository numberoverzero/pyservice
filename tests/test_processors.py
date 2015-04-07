import ujson
import pytest
import collections
from pyservice import processors, Client


class RequestPostCapture:
    class Response:
        def __init__(self, status_code, text, reason=None):
            self.status_code = status_code
            self.text = text
            self.reason = reason

    def __init__(self, status_code, text, reason=None):
        self.response = self.Response(status_code, text, reason=reason)

    def post(self, uri, data, timeout):
        self.uri = uri
        self.data = data
        self.timeout = timeout
        return self.response


@pytest.fixture
def with_post(monkeypatch):
    def make_capture(status_code, text, reason=None):
        capture = RequestPostCapture(status_code, text, reason=reason)
        monkeypatch.setattr("requests.post", capture.post)
        return capture
    return make_capture


class TestProcessor(processors.Processor):
    ''' Processor that tracks _execute, enter|exit scope, and result calls '''
    def __init__(self, operation, result):
        super().__init__(Client(), operation)
        self.calls = collections.defaultdict(int)
        self._result = result

    def _execute(self):
        self.calls["_execute"] += 1

    def enter_scope(self, scope):
        self.calls[("enter_scope", scope)] += 1

    def exit_scope(self, scope):
        self.calls[("exit_scope", scope)] += 1

    @property
    def result(self):
        self.calls["result"] += 1
        return self._result


def test_processor_workflow():
    ''' Ensure enter|exit scope and _execute are all called once '''
    operation = "my_operation"
    expected_result = "this is the result"
    process = TestProcessor(operation, expected_result)
    assert not process.calls

    result = process()

    assert result == expected_result
    assert process.calls["_execute"] == 1
    for func in ["enter_scope", "exit_scope"]:
        for scope in ["request", "operation", "function"]:
            assert process.calls[(func, scope)] == 1


def test_processor_multiple_calls():
    ''' Can't process more than once '''
    process = TestProcessor("not used", "also not used")
    process()

    with pytest.raises(RuntimeError):
        process()


def test_processor_plugin_scopes():
    ''' Ensure plugins in request and operation scopes are invoked '''
    operation = "my_operation"
    process = TestProcessor(operation, "not used")

    called = []

    @process.obj.plugin(scope="request")
    def request_plugin(context):
        called.append("request")
        assert context.operation == operation
        context.process_request()

    @process.obj.plugin(scope="operation")
    def operation_plugin(request, response, context):
        called.append("operation")
        assert context.operation == operation
        context.process_request()

    process()
    assert called == ["request", "operation"]


def test_client_processor_posts(client, with_post):
    ''' Result should be unpacked from request.post '''
    operation = "foo"
    request = {"key": "value"}
    process = processors.ClientProcessor(client, operation, request)

    status_code = 200
    text = ujson.dumps({"greeting": ["Hello", "World!"]})
    request_capture = with_post(status_code, text)

    result = process()
    assert result.greeting == ["Hello", "World!"]

    assert request_capture.uri == "http://localhost:8080/test/foo"
    assert ujson.loads(request_capture.data) == request


def test_client_handle_http_error(client, with_post):
    '''
    ClientProcessor should raise a real exception when the status is not 200
    '''
    operation = "foo"
    request = {"key": "value"}
    process = processors.ClientProcessor(client, operation, request)
    with_post(404, '', reason="Not Found")

    with pytest.raises(client.exceptions.RequestException):
        process()


def test_client_handle_remote_error(client, with_post):
    ''' Correctly raise a remote exception '''
    operation = "foo"
    request = {"key": "value"}
    process = processors.ClientProcessor(client, operation, request)

    exception_text = ujson.dumps({
        "__exception__": {
            "cls": "FooExceptionClass",
            "args": ("text", 1, False)
        },
        "extra": {
            "this should not": "be accessible"
        }
    })
    with_post(200, exception_text)

    # Make sure we actually raise
    with pytest.raises(getattr(client.exceptions, "FooExceptionClass")):
        process()


def test_client_debug_remote_error(client, with_post):
    '''
    Plugins should have access to the response body after an
    exception when we're debugging
     '''
    operation = "foo"
    request = {"key": "value"}
    exception = getattr(client.exceptions, "FooExceptionClass")
    process = processors.ClientProcessor(client, operation, request)

    exception_text = ujson.dumps({
        "__exception__": {
            "cls": exception.__name__,
            "args": (2, 'args')
        },
        "extra": {
            "this should": "be available"
        }
    })
    with_post(200, exception_text)
    captured_response = {}

    @client.plugin(scope="operation")
    def capture_extra(request, response, context):
        try:
            context.process_request()
        except exception:
            captured_response.update(response)

    # Don't clear response on exception
    client.api["debug"] = True

    process()

    assert captured_response["extra"] == {"this should": "be available"}


def test_service_processor_invokes_function(service):
    ''' The mapped function for the operation should be called '''

    called = False
    request_body = ujson.dumps({"key": "value"})

    @service.operation("foo")
    def foo(request, response, context):
        nonlocal called
        called = True

        assert request.key == "value"

    process = processors.ServiceProcessor(service, "foo", request_body)

    assert not called
    process()
    assert called


def test_service_processor_raises_whitelisted(service):
    ''' Serialize and return a whitelisted exception '''

    service.api["exceptions"].append("FooException")

    @service.operation("foo")
    def foo(request, response, context):
        raise service.exceptions.FooException(2, "args")

    process = processors.ServiceProcessor(service, "foo", "{}")
    result = process()

    expected = {
        "__exception__": {
            "cls": "FooException",
            "args": [2, "args"]
        }
    }
    assert ujson.loads(result) == expected


def test_service_processor_raises_debugging(service):
    ''' Serialize and return non-whitelist when debugging '''

    @service.operation("foo")
    def foo(request, response, context):
        raise service.exceptions.FooException(2, "args")

    process = processors.ServiceProcessor(service, "foo", "{}")

    # Don't redact exception when debugging
    service.api["debug"] = True
    result = process()

    expected = {
        "__exception__": {
            "cls": "FooException",
            "args": [2, "args"]
        }
    }
    assert ujson.loads(result) == expected


def test_service_processor_redacts_non_whitelist(service):
    ''' Scrub non-whitelist exception data when not debugging '''

    @service.operation("foo")
    def foo(request, response, context):
        raise service.exceptions.FooException(2, "args")

    process = processors.ServiceProcessor(service, "foo", "{}")

    # Don't redact exception when debugging
    result = process()

    expected = {
        "__exception__": {
            "cls": "RequestException",
            "args": [500]
        }
    }
    assert ujson.loads(result) == expected
