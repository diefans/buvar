"""Dependency injection.

Register a class, function or method to adapt arguments into something else.

>>> class Bar:
...     pass

>>> @adapter
... class Foo:
...     def __init__(self, bar: Bar):
...         self.bar = bar

...     @adapter_classmethod
...     def adapt(cls, bar: Bar) -> Foo:
...         return cls(bar)

>>> @adapter
... def adapt(bar: Bar) -> Foo:
...     return Foo(bar)

"""
try:
    # gains over 100% speed up
    from .c_di import Adapters
except ImportError:
    from .py_di import Adapters  # noqa: W0611

defaults_adapters = Adapters()
adapter_classmethod = defaults_adapters.adapter_classmethod
adapter = defaults_adapters.adapter
nject = defaults_adapters.nject
