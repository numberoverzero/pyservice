import pytest
import collections
from pyservice import processors


class PluginObj:
    ''' Mock client/service with plugins '''
    def __init__(self):
        self.plugins = {
            "request": [],
            "operation": []
        }


class TestProcessor(processors.Processor):
    ''' Processor that tracks _execute, enter|exit scope, and result calls '''
    def __init__(self, operation, result):
        obj = PluginObj()
        super().__init__(obj, operation)
        self.calls = collections.defaultdict(int)
        self._plugin_obj = obj
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

    def request_plugin(context):
        called.append("request")
        assert context.operation == operation
        context.process_request()
    process._plugin_obj.plugins["request"].append(request_plugin)

    def operation_plugin(request, response, context):
        called.append("operation")
        assert context.operation == operation
        context.process_request()
    process._plugin_obj.plugins["operation"].append(operation_plugin)

    process()
    assert called == ["request", "operation"]
