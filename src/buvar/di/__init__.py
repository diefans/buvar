"""Dependency injection.

Register a class, function or method to adapt arguments into something else.

>>> class Bar:
...     pass

>>> @register
... class Foo:
...     def __init__(self, bar: Bar):
...         self.bar = bar

...     @register_classmethod
...     def adapt(cls, bar: Bar) -> Foo:
...         return cls(bar)

>>> @register
... def adapt(bar: Bar) -> Foo:
...     return Foo(bar)

"""
from . import adapter

register_classmethod = adapter.Adapter.from_classmethod
register = adapter.Adapter.from_func

try:
    # gains over 100% speed up
    from .c_resolve import nject
except ImportError:
    from .resolve import nject  # noqa: W0611
