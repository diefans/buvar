"""Dependency injection.

Register a class, function or method to adapt arguments into something else.

>>> class Bar:
...     pass

>>> class Foo:
...     def __init__(self, bar: Bar):
...         self.bar = bar
...     @classmethod
...     def adapt(cls, bar: Bar) -> 'Foo':
...         return cls(bar)

>>> def adapt() -> Bar:
...     return Bar()

>>> adapters = Adapters()
>>> adapters.register(Bar)
>>> adapters.register(Foo.adapt)
>>> adapters.register(adapt)

>>> import asyncio
>>> loop = asyncio.get_event_loop()
>>> foo = loop.run_until_complete(adapters.nject(Foo))
>>> assert isinstance(foo, Foo)

"""

import abc
import contextvars as cv
import functools as ft
import inspect
import itertools as it
import sys
import typing as t

import typing_inspect as ti

from buvar import util
from .exc import ResolveError, missing


try:
    # gains over 100% speed up
    from . import c_di as _impl

except ImportError:
    from . import py_di as _impl


PY_39 = sys.version_info >= (3, 9)


class AdapterError(Exception):
    pass


class Adapters(dict, _impl.AdaptersImpl):
    def __init__(self):
        super().__init__()
        self.context = cv.copy_context()

    def __hash__(self):
        # since we want to cache our lookup, we need have to be hashable
        return object.__hash__(self)

    def register(self, *implementations, frame=None, **kwargs):
        frame = frame or sys._getframe(1)
        for implementation in implementations:
            adapter = Adapter(implementation, frame=frame)
            adapter.register(self, **kwargs)
        # self.lookup.cache_clear()

    # @ft.lru_cache(maxsize=None)
    def lookup(self, tp):
        errors = {}

        def collect():
            for adapter_cls in reversed(Adapter.classes):
                try:
                    yield from adapter_cls.lookup(self, tp)
                except Exception as ex:
                    errors[adapter_cls] = ex

        return set(collect())


class AdapterMeta(abc.ABCMeta):
    classes = []

    def __call__(cls, implementation, *, frame=None):
        frame = frame or sys._getframe(1)
        errors = {}
        # polymorphic instantiation: trial and error from specific to generic
        for adapter_cls in reversed(cls.classes):
            try:
                adapter = type.__call__(adapter_cls, implementation, frame=frame)
                return adapter
            except Exception as ex:
                errors[adapter_cls] = ex
        if errors:
            raise AdapterError("All adaptations failed", errors)
        raise AdapterError("No adapters")


class Adapter(metaclass=AdapterMeta):
    def __init__(self, implementation, **_):
        self.implementation = implementation

    def __init_subclass__(cls):
        if not inspect.isabstract(cls):
            cls.classes.append(cls)

    @abc.abstractmethod
    def register(self, registry: t.Dict):
        """Register this adapter into the registry."""

    @abc.abstractclassmethod
    def lookup(cls, registry: t.Dict, tp) -> t.Iterator:
        """Lookup an adapter based on its return type."""

    if sys.version_info >= (3, 8):

        async def create(self, target, *args, **kwargs):
            call = self.implementation(*args, **kwargs)
            return (
                await call if inspect.iscoroutinefunction(self.implementation) else call
            )

    else:

        async def create(self, target, *args, **kwargs):
            call = self.implementation(*args, **kwargs)
            if isinstance(self.implementation, ft.partial):
                return (
                    await call
                    if inspect.iscoroutinefunction(self.implementation.func)
                    else call
                )
            else:
                return (
                    await call
                    if inspect.iscoroutinefunction(self.implementation)
                    else call
                )


def evaluate(tp: t.Union[str, t.TypeVar, t.Type, t.ForwardRef], *, frame=None):
    if isinstance(tp, str):
        tp = t.ForwardRef(tp)

    if ti.is_typevar(tp):
        tp = ti.get_bound(tp)

    # TODO python versions
    return t._eval_type(
        tp,
        frame.f_globals if frame else None,
        frame.f_locals if frame else None,
    )


def evaluated_signature(func: t.Callable, frame=None):
    """Adjust annotations."""
    signature = inspect.Signature.from_callable(func)
    signature = signature.replace(
        parameters=[
            p.replace(
                annotation=evaluate(p.annotation, frame=frame),
                default=p.default
                # we change empty to missing for later convenience
                if p.default is not inspect.Signature.empty
                else missing,
            )
            for p in signature.parameters.values()
        ],
        return_annotation=evaluate(signature.return_annotation, frame=frame),
    )
    return signature


class BaseMatrix:
    def __call__(self, tp):
        if inspect.isclass(tp):
            return self.iter_mro(tp)
        if ti.is_optional_type(tp):
            return self.iter_optional(tp)
        if ti.is_tuple_type(tp):
            return self.iter_generic(tp)
        if ti.is_union_type(tp):
            return self.iter_generic(tp)
        if ti.is_generic_type(tp):
            return self.iter_generic(tp)

    def iter_mro(self, tp):
        mro = inspect.getmro(tp)
        # skip object
        yield from iter(mro[:-1])

    def iter_optional(self, tp):
        arg, *_ = ti.get_args(tp, evaluate=True)
        for base in self(arg):
            yield t.Optional[base]

    def iter_generic(self, tp):
        args = ti.get_args(tp, evaluate=True)
        yield from (tp.copy_with(params) for params in it.product(*map(self, args)))


base_matrix = BaseMatrix()


class CallableAdapter(Adapter, inspect.Signature):
    def __init__(self, implementation, *, frame=None):
        if not callable(implementation):
            raise AdapterError("Implementation not callable", implementation)
        super().__init__(implementation)
        self.frame = frame
        signature = evaluated_signature(self.implementation, frame=frame)
        inspect.Signature.__init__(
            self,
            list(signature.parameters.values()),
            return_annotation=signature.return_annotation,
        )

    def __hash__(self):
        # INFO:we hash the signature and the implementation, because signature
        # may be the same for different implememtations
        return hash(
            (super(inspect.Signature, self).__hash__(), hash(self.implementation))
        )

    def __repr__(self):
        return f"<{self.__class__.__name__}[{self.implementation}] {self.parameters}"

    @util.cached
    def return_type(self):
        rt = self.return_annotation
        if rt is not inspect.Signature.empty and rt is not None:
            return rt
        if inspect.isclass(self.implementation):
            return self.implementation
        raise AdapterError(
            "Adapter implementation has no return type", self.implementation
        )


class GenericAdapter(CallableAdapter):
    def __init__(self, implementation, *, frame=None):
        super().__init__(implementation, frame=frame)

    @classmethod
    def registry(cls, registry: t.Dict):
        registry = registry.setdefault(cls, {})
        return registry

    def register(self, registry: t.Dict, replace: bool = False):
        registry = self.registry(registry)
        for base in base_matrix(self.return_type):
            if replace:
                registry[base] = {self}
            else:
                registry.setdefault(base, set()).add(self)

    @classmethod
    def lookup(cls, registry: t.Dict, tp):
        registry = cls.registry(registry)
        adapters = registry.get(tp)
        if adapters:
            yield from adapters


class MethodAdapter(GenericAdapter):
    def __init__(self, implementation, *, frame=None):
        super().__init__(implementation, frame=frame)
        if not inspect.ismethod(implementation):
            raise AdapterError("Implementation is not a method", implementation)


class ClassmethodAdapter(MethodAdapter):
    def __init__(self, implementation, *, frame=None):
        super().__init__(implementation, frame=frame)
        if not inspect.isclass(implementation.__self__):
            raise AdapterError("Implementation is not a classmethod", implementation)
        self.cls = implementation.__self__

    @classmethod
    def lookup(cls, registry: t.Dict, tp):
        """
        Foo <- Bar(Foo) <- Baz(Bar)
          |
          +-- adapt(cls) -> "Foo"

        An implementation returning parent is registered.

        We want to have an instance of `Bar` or `Baz`.
        If we do not find an adapter directly, we try to find an adapter, which
        returns a subclass of `Bar` or `Baz` and whose class is also this
        subclass
        """
        yield from super().lookup(registry, tp)
        local_registry = cls.registry(registry)
        # try inheritance
        for base in inspect.getmro(tp)[:-1]:
            for adapter in local_registry.get(base, ()):
                # found an adater which returns a base
                if issubclass(base, adapter.cls):
                    # found an adapter, whose class matches what he returns
                    # we prebind our implementation
                    bound_adapter = adapter.replace(
                        # TODO XXX FIXME partial only works in >=3.8
                        # create is not recognizing coroutine
                        ft.partial(adapter.implementation.__func__, tp)
                    )
                    # cache
                    local_registry.setdefault(tp, set()).add(bound_adapter)
                    yield bound_adapter

    def replace(self, implementation):
        adapter = type(self)(implementation, frame=self.frame)
        return adapter


# our default adapters
buvar_adapters = cv.ContextVar(__name__)
buvar_adapters.set(Adapters())


def register(*impls, **kwargs):
    adapters = buvar_adapters.get()
    adapters.register(*impls, frame=sys._getframe(1), **kwargs)


async def nject(*targets, **dependencies):
    adapters = buvar_adapters.get()
    return await adapters.nject(*targets, **dependencies)
