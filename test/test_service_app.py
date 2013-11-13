import json
import webtest
j = json.loads

import pyservice

def test_service_routing():
    data = j('{"name": "ServiceName", "operations": [{"name":"ConcatOperation", "input": ["a", "b"], "output": ["ab"]}]}')
    service = pyservice.parse_service(data)

    @service.operation("ConcatOperation")
    def concat(a, b):
        return a + b

    input = {"a": "Hello", "b": "World"}
    route = "/ServiceName/ConcatOperation"

    app = webtest.TestApp(service._app)
    response = app.post_json(route, input)

    assert response.json == {"ab": "HelloWorld"}
