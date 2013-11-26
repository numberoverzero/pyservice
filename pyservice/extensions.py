from pyservice.layer import Layer

class ClientAuthLayer(Layer):

    def handle_request(self, context, next):
        client = context["client"]
        key = client._attr("authuser", None)
        pw = client._attr("authpw", None)
        if key is None or pw is None:
            raise ValueError("Must provide authuser and authpw")
        next.handle_request(context)

class ServiceAuthLayer(Layer):

    def handle_request(self, context, next):
        op_input = context["input"]
        key = op_input.get("authuser", None)
        pw = op_input.get("authpw", None)
        if key is None or pw is None:
            raise ValueError("Must provide authuser and authpw")
        next.handle_request(context)