from pyservice.operation import handle_request

def handle(service, operation, body):
    return handle_request(service, operation, operation._func, body)