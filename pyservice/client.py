import logging
import functools
import requests
import ujson
from .common import (
    cache,
    DEFAULT_CONFIG,
    Extensions,
    ExceptionFactory
)
logger = logging.getLogger(__name__)


class Client(object):
    def __init__(self, description, **config):
        self.config = dict(DEFAULT_CONFIG)
        self.config.update(config)
        self.operations = {}
        self.exceptions = ExceptionFactory()

        # Add __handle after all extensions
        self.extensions = Extensions(
            lambda: self.extensions.append(self.__handle))
        self.__description = description

        uri = "{scheme}://{host}:{port}{path}".format(
            **self.__description.endpoint)
        self.uri = uri.format(
            protocol=self.config["protocol"],
            version=self.__description.version,
            operation="{operation}")
        logger.info("Service uri is {}".format(self.uri))

        # Bind operations to self
        for operation in self.__description.operations:
            func = functools.partial(self, operation)
            self.operations[operation] = func
            setattr(self, operation, func)

    @cache
    def debugging(self):
        return self.config.get("debug", False)

    def __call__(self, operation, **request):
        if self.debugging:
            logger.info("call(operation={o}, request={r})".format(
                o=operation, r=request))
        context = {
            "exception": {},

            # Meta for this operation
            "operation": operation,
            "description": self.__description,
            "client": self
        }

        successful_response = False
        try:
            self.extensions("before_operation", operation, context)

            # before/after don't have acces to request/response
            context["request"] = request
            context["response"] = {}

            self.extensions("operation", operation, context)
            successful_response = True

            # before/after don't have acces to request/response
            result = context["response"]
            del context["request"]
            del context["response"]

            return result
        finally:
            self.extensions("after_operation", operation, context)

    def __handle(self, next_handler, event, operation, context):
        if self.debugging:
            logger.debug("handle(event={event}, context={context})".format(
                event=event, context=context))
        if event == "operation":
            try:
                wire_out = ujson.dumps(
                    {"request": context["request"]})
                wire_in = requests.post(
                    self.uri.format(operation=operation),
                    data=wire_out, timeout=self.config["timeout"])
                wire_in.raise_for_status()
                r = ujson.loads(wire_in.text)
                for key in ["response", "exception"]:
                    context[key].update(r.get(key, {}))
            except Exception as exception:
                msg = "Exception during operation {}".format(operation)
                if self.debugging:
                    logger.exception(msg, exc_info=exception)
                raise

            if context["exception"]:
                # Raise here so surrounding extensions can try/catch
                self.__raise_exception(operation, context)
            else:
                next_handler(event, operation, context)
        else:
            # Pass through
            next_handler(event, operation, context)

    def __raise_exception(self, operation, context):
        '''
        Exception classes are generated from the external client,
        since all consumers will be catching against
        external client.exceptions.
        '''

        exception = context["exception"]
        name = exception["cls"]
        args = exception["args"]
        exception = getattr(self.exceptions, name)(*args)

        exceptions = self.__description.operations[operation].exceptions
        whitelisted = name in exceptions
        if self.debugging:
            logger.debug("raise_exception(whitelist={w})".format(
                w=whitelisted))

        if not (whitelisted or self.debugging):
            # Not debugging and not an expected exception,
            # wrap so it doesn't bubble up
            wrap = self.exceptions.ServiceException
            exception = wrap(*[
                "Unknown exception for operation {}".format(operation),
                exception
            ])
        raise exception
