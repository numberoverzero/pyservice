import inspect
"""
Modified from Lib/inspect.py to allow extra keyword args,
and skip all positional processing
"""

def signature(obj):
    return CustomSignature.from_callable(obj)


class CustomSignature(inspect.Signature):
    """
    What is this voodoo sorcery?  See:
        https://docs.python.org/3/library/inspect.html#inspect.Signature.bind
        https://docs.python.org/3/library/inspect.html#inspect.BoundArguments
    This subclass has two key differences:
        `bind` doesn't process positional args at all
        `bind` doesn't throw on extra kwargs not mapped in the signature
    """
    def bind(self, **kwargs):
        # TODO:
        #   rip out arg processing from Signature._bind
        #   don't throw on extra kwargs
        pass
