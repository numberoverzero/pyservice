"""
These classes are responsible for managing state during a client/service
request, particularly to minimize the burden on plugins to manage context
"""
from . import common
from . import wsgi
import requests
missing = object()


def service(service, operation, request_body):  # pragma: no cover
    ''' Wrap the Processor class to match the __processor__ interface '''
    return ServiceProcessor(service, operation, request_body)()


def client(client, operation, request_body):  # pragma: no cover
    ''' Wrap the Processor class to match the __processor__ interface '''
    return ClientProcessor(client, operation, request_body)()


class Processor(object):
    def __init__(self, obj, operation):
        """
        Simplifies the chaining contract for plugin authors.  This allows a
        plugin to use context.process_request() without passing the request,
        response, and context objects back into the chained call, and without
        keeping track of the correct next plugni to call.
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
        self.scope = "request"
        self.transitions = {
            "request": "operation",
            "operation": "function",
            "function": None
        }
        self.index = -1

    def __call__(self):
        """ Entry point for external callers to begin processing """
        if self.scope is None:
            raise RuntimeError("Already processed request")
        self.process_request()
        return self.result

    def process_request(self):
        """
        Public re-entry point.

        Plugins will come in through commons.Context.process_request, which
        will delegate to its processor's continue_exection (usually this
        method).  The internal _continue method will also call into this
        function, to keep state management (request-> operation -> function)
        separate from lifecycle management (enter|exit scope, execute).
        """
        # If this is the first time we've been in this scope,
        # give subclasses a chance to (de)serialize, load/dump containers, etc
        is_first_plugin = self.index == -1

        # Keep a reference to the scope in this function call, since we know
        # self.scope will mutate as this recurses
        local_scope = self.scope

        if is_first_plugin:
            self.enter_scope(local_scope)

        self._continue()

        # If we called enter_scope in this scope, then we also need to call
        # exit_scope in this scope (the rest of this scope was executed in)
        # one of the recursive calls above
        if is_first_plugin:
            self.exit_scope(local_scope)

    def _continue(self):
        ''' Call the next plugin '''
        # When scope is function, there won't be any plugins
        plugins = self.obj.plugins.get(self.scope, [])
        n = len(plugins)
        self.index += 1

        # We just processed the last plugin for this scope, either roll over
        # to the next scope or invoke the function underneath it all
        if self.index == n:

            # Determine the next scope and continue execution
            next_scope = self.transitions.get(self.scope, missing)
            if next_scope is not missing:
                self.scope = next_scope
                self.index = -1
                self.process_request()
            # Otherwise, we've finished the last set of scoped plugins
            # (function) and need to call the underlying function
            else:
                self._execute()

        # We're still working through the plugins for this scope
        else:  # self.index < n
            # This is an assert instead of an exception because there's no
            # single best way to recover from walking off the end of the
            # available plugins - return, increment scope, raise?
            assert self.index < n, "index exceeded length of plugins"

            if self.scope == "request":
                plugins[self.index](self.context)
            elif self.scope == "operation":
                plugins[self.index](self.request, self.response, self.context)
            # Don't know how to handle plugins of other types, this is likely
            # a bug.  Raise an error immediately instead of silently hanging
            else:  # pragma: no cover
                raise ValueError("Unexpected scope '{}'".format(self.scope))

    def _execute(self):  # pragma: no cover
        raise NotImplementedError("Subclasses must implement _execute.")

    def enter_scope(self, scope):  # pragma: no cover
        ''' The scope whose execution is about to begin '''
        pass

    def exit_scope(self, scope):  # pragma: no cover
        ''' The scope whose execution just finished '''
        pass

    @property
    def result(self):  # pragma: no cover
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
        3. Call the endpoint with the packed request
        4. Raise native errors on http failure
        5. Unpack the response
        6. Raise native errors on service exceptions
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
            # Don't need to persist the result since we'll
            # return self.result below anyway
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

    def enter_scope(self, scope):
        # Unpack request_body so it's available to operation scoped plugins
        if scope == "operation":
            common.deserialize(self.request_body, self.request)

    def exit_scope(self, scope):
        # Pack response into response body so we can ship it back on the wire
        # It's important to do this before the request-scope plugins clean up,
        # since their scope may be required to serialize the response body
        if scope == "operation":
            self.response_body = common.serialize(self.response)

    @property
    def result(self):
        return self.response_body

    def raise_exception(self, exception):
        '''
        Because this can occurr when exit_scope('operation') has already
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
