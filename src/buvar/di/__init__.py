"""Dependency injection."""
import functools
import inspect
import itertools

from . import adapter


class register:
    """Register a class, function or method to adapt arguments into something else.

    >>> class Bar:
    ...     pass

    >>> @register
    ... class Foo:
    ...     def __init__(self, bar: Bar):
    ...         self.bar = bar

    ...     @register
    ...     def adapt(cls, bar: Bar) -> Foo:
    ...         return cls(bar)

    >>> @register
    ... def adapt(bar: Bar) -> Foo:
    ...     return Foo(bar)

    """

    def __new__(cls, func):
        instance = super().__new__(cls)
        if inspect.isclass(func):
            instance.__init__(func)
            return func
        return instance

    def __init__(self, func):
        currentframe = inspect.currentframe()
        spec = inspect.getfullargspec(func)
        if inspect.isclass(func):
            # we remove self from class specs
            spec.args.pop(0)

        implements = func if inspect.isclass(func) else spec.annotations["return"]

        # all none defaults must be annotated
        defaults = dict(
            itertools.chain(
                zip(reversed(spec.args or []), reversed(spec.defaults or [])),
                (spec.kwonlydefaults or {}).items(),
            )
        )

        self.adapter = adapter.Adapter(
            func=func,
            spec=spec,
            frame=currentframe,
            # globals=frame.f_globals,
            # locals=frame.f_locals,
            owner=None,
            name=None,
            defaults=defaults,
            implements=implements,
        )
        adapter.adapters[implements].append(self.adapter)

    def __set_name__(self, owner, name):
        self.adapter.owner = owner
        self.adapter.name = name
        # remove cls from args
        self.adapter.spec.args.pop(0)

        try:
            hints = self.adapter.hints
            self.adapter.implements = hints["return"]
            adapter.adapters[hints["return"]].append(self.adapter)
        except NameError:
            pass

    def __get__(self, instance, owner=None):
        if owner is None:
            owner = type(instance)
        return functools.partial(self.adapter.func, owner)

    def __call__(self, *args, **kwargs):
        return self.adapter.func(*args, **kwargs)


try:
    # gains over 100% speed up
    from .c_resolve import nject
except ImportError:
    from .resolve import nject  # noqa: W0611
