"""
These classes are responsible for managing state during a client/service
request, particularly to minimize the burden on plugins to manage context
"""
from . import common
from . import wsgi
import requests


def service(service, operation, request_body):
    process = ServiceProcessor(service, operation, request_body)
    return process()


def client(client, operation, request_body):
    process = ClientProcessor(client, operation, request_body)
    return process()


class Processor(object):
    def __init__(self, obj, operation):
        """
        A python class with __init__ and 1 or 2 functions is usually an
        anti-pattern, but in this case we're using it to simplify the
        chaining contract for plugin authors.  This allows them to
        use context.process_request() without managing the state to pass
        to the next plugin, or in any way knowing if there is another plugin
        """
        self.obj = obj
        # Don't rely on context's operation to be immutable
        self.operation = operation

        self.context = common.Context(self)
        self.context.operation = operation

        self.request = common.Container()
        self.request_body = None
        self.response = common.Container()
        self.response_body = None

        # request -> operation -> function
        self.state = "request"
        self.transitions = {
            "request": "operation",
            "operation": "function",
            "function": None
        }
        self.index = -1

    def __call__(self):
        """ Entry point for external callers """
        if self.state is None:
            raise ValueError("Already processed request")
        self.continue_execution()
        return self.result

    def continue_execution(self):
        # If this is the first time we've been in this state,
        # give subclasses a chance to (de)serialize, load/dump containers, etc
        call_after_state = False
        if self.index == -1:
            self.before_state(self.state)
            # Since we're about to invoke the first plugin for this state,
            # the recursive call will go through all remaining plugins for this
            # state.  After that recursive call, this scope will be the first
            # point after all plugins at this state ran, and we should call
            # self.after_state(self.state).  However, self.state will have
            # mutated (since this is recursive).  Therefore we store the state
            # to invoke after_state with in the variable.
            call_after_state = self.state

        # We don't recurse for the next plugin during 'function' since there
        # shouldn't be any function-scope plugins.
        if self.state in ["request", "operation"]:
            self._continue()
        # We've made it!  Make the remote call or invoke the service handler
        elif self.state == "function":
            self._execute()

        # If we called before_state in this scope, then we also need to call
        # after_state in this scope (the rest of this scope was executed in)
        # one of the recursive calls above
        if call_after_state:
            self.after_state(call_after_state)

    def _continue(self):
        ''' Call the next plugin '''
        self.index += 1
        # When state is function, there won't be any plugins
        plugins = self.obj.plugins.get(self.state, [])
        n = len(plugins)

        # We're still working through the plugins for this scope
        if self.index < n:
            if self.state == "request":
                plugins[self.index]()
            elif self.state == "operation":
                plugins[self.index](self.request, self.response, self.context)
            else:
                raise ValueError("Unexpected state '{}'".format(self.state))

        # We just processed the last plugin for this state, either roll over
        # to the next state or invoke the function underneath it all
        elif self.index == n:

            # Determine the next state and continue execution
            if self.transitions[self.state]:
                self.state = self.transitions[self.state]
                self.index = -1
                self.continue_execution()

            # Otherwise this is a continue_execution call during the 'function'
            # state and we can safely ignore it
            else:
                pass

    def _execute(self):
        raise NotImplementedError("Subclasses must implement _execute.")

    def before_state(self, state):
        ''' The state whose execution is about to begin '''
        pass

    def after_state(self, state):
        ''' The state whose execution just finished '''
        pass

    @property
    def result(self):
        raise NotImplementedError("Subclasses must define result.")


class ClientProcessor(Processor):
    def __init__(self, client, operation, request):
        super().__init__(client, operation)
        self.context.client = client
        self.request.update(request)

    def _execute(self):
        '''
        1. Pack the request
        2. Construct the endpoint
        3. Unpack the response
        4. Raise native errors if necessary
        '''

        self.request_body = common.serialize(self.request)

        pattern = self.obj.api["endpoint"]["client_pattern"]
        uri = pattern.format(operation=self.operation)
        data = self.request_body
        timeout = self.obj.api["timeout"]
        response = requests.post(uri, data=data, timeout=timeout)

        self.handle_http_error(response)
        self.response_body = response.text
        common.deserialize(self.response_body, self.response)
        self.handle_service_exception()

    @property
    def result(self):
        return self.response

    def handle_http_error(self, response):
        if wsgi.is_request_exception(response):
            message = "{} {}".format(response.status_code, response.reason)
            self.raise_exception({
                "cls": "RequestException",
                "args": (message,)
            })

    def handle_service_exception(self):
        exception = self.response.get("__exception__", None)
        if exception:
            # Don't leak incomplete operation state if we're not debugging
            if not self.obj.api["debug"]:
                self.response.clear()
            self.raise_exception(exception)

    def raise_exception(self, exception):
        name = exception["cls"]
        args = exception["args"]
        raise getattr(self.obj.exceptions, name)(*args)


class ServiceProcessor(Processor):
    def __init__(self, service, operation, request_body):
        super().__init__(service, operation)
        self.context.service = service
        self.request_body = request_body

    def __call__(self):
        '''
        Wrap exceptions so they can be serialized back to the client.

        Exceptions that are thrown anywhere in the plugin chain may be allowed
        to serialize back to the client, so we have to try/except the entire
        call chain.
        '''
        try:
            super().__call__()
        except Exception as exception:
            self.raise_exception(exception)
        finally:
            return self.result

    def _execute(self):
        '''
        Invoke the service's function for the current operation
        '''
        func = self.obj.functions[self.operation]
        func(self.request, self.response, self.context)

    def before_state(self, state):
        # Unpack request_body so it's available to operation scoped plugins
        if state == "operation":
            common.deserialize(self.request_body, self.request)

    def after_state(self, state):
        # Pack response into response body so we can ship it back on the wire
        # It's important to do this before the request-scope plugins clean up,
        # since their state may be required to serialize the response body
        if state == "operation":
            self.response_body = common.serialize(self.response)

    @property
    def result(self):
        return self.response_body

    def raise_exception(self, exception):
        '''
        Because this can occurr after after_state('operation') has already
        fired, we have to make sure we re-serialize the response body.
        '''
        name = exception.__class__.__name__
        args = exception.args

        # Don't let non-whitelisted exceptions escape if we're not debugging
        whitelisted = name in self.obj.api["exceptions"]
        debugging = self.obj.api["debug"]
        if not whitelisted and not debugging:
            raise wsgi.INTERNAL_ERROR

        # Don't leak incomplete operation state
        self.response.clear()
        self.response["__exception__"] = {
            "cls": name,
            "args": args
        }
        self.response_body = common.serialize(self.response)
