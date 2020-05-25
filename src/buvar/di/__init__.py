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
try:
    # gains over 100% speed up
    from .c_di import AdaptersImpl
except ImportError:
    from .py_di import AdaptersImpl


import contextvars
import collections
import inspect
import itertools
import sys
import types
import typing

import typing_inspect

from buvar import util

from .exc import ResolveError, missing


class AdapterError(Exception):
    pass


class SignatureMeta(type):
    classes = {}

    def __new__(mcs, name, bases, dct):
        cls = type.__new__(mcs, name, bases, dct)
        mcs.classes[name] = cls
        return cls

    def __call__(cls, impl, *, frame=None, **kwargs):
        # try classes from latest to oldest
        for adapter_cls in reversed(list(cls.classes.values())):
            args = adapter_cls.test_impl(impl, frame=frame)
            if args:
                inst = type.__call__(adapter_cls, impl, **args)
                return inst
        raise TypeError("No adapter implementation found", impl)


class Adapter(metaclass=SignatureMeta):
    def __init__(self, impl, *, spec, hints):
        self.impl = impl
        self.spec = spec
        self.hints = hints
        self.args = self._create_args()

    @classmethod
    def test_impl(cls, impl, *, frame):
        # TODO test for sane hints
        if callable(impl):
            return get_annotations(impl, frame=frame)

    @util.reify
    def target(self):
        return self.hints["return"]

    def register(self, adapters):
        if self.lookup not in adapters.lookups:
            adapters["index"] = collections.defaultdict(list)
            adapters.lookups[self.lookup] = True
        adapters["index"][self.target].insert(0, self)

    @staticmethod
    def lookup(adapters, target):
        if target in adapters["index"]:
            yield from adapters["index"][target]

    def _filter_arg_name(self, name):
        return False

    def _create_args(self):
        hints = self.hints
        defaults = collect_defaults(self.spec)
        args = [
            (name, extract_optional_type(hints[name]), defaults.get(name, missing))
            for name in itertools.chain(self.spec.args, self.spec.kwonlyargs)
            if not self._filter_arg_name(name)
        ]

        return args

    async def create(self, target, *args, **kwargs):
        impl = self.impl
        call = impl(*args, **kwargs)
        return await call if inspect.iscoroutinefunction(impl) else call


class ClassAdapter(Adapter):
    @util.reify
    def target(self):
        return self.impl

    @classmethod
    def test_impl(cls, impl, *, frame):
        if isinstance(impl, type):
            return super().test_impl(impl.__init__, frame=frame)

    def _filter_arg_name(self, name):
        return name is self.spec.args[0]


class ClassmethodAdapter(Adapter):
    @classmethod
    def test_impl(cls, impl, *, frame):
        if isinstance(impl, types.MethodType) and isinstance(impl.__self__, type):
            return super().test_impl(impl.__func__, frame=frame)

    def _filter_arg_name(self, name):
        return name is self.spec.args[0]


class GenericFactoryAdapter(ClassmethodAdapter):
    def __init__(self, impl, *, spec, hints, cls_type, bound):
        super().__init__(impl, spec=spec, hints=hints)
        self.cls_type = cls_type
        self.bound = bound

    @classmethod
    def test_impl(cls, impl, *, frame):
        args = super().test_impl(impl, frame=frame)
        if not args:
            return
        cls_attr = args.spec.args[0]
        generic_type = args.hints.get(cls_attr)
        # https://mypy.readthedocs.io/en/latest/generics.html#generic-methods-and-generic-self
        if (
            generic_type
            and generic_type.__origin__ is type
            and typing_inspect.is_generic_type(generic_type)
        ):
            cls_type, = typing_inspect.get_args(generic_type)
            target = args.hints["return"]

            # assure bound type equals classmethod owner
            if cls_type is target:
                bound = typing_inspect.get_bound(cls_type)
                if bound:
                    # we use frame locals to enable references within function scope
                    bound = bound._evaluate(impl.__func__.__globals__, frame.f_locals)
                    if bound is impl.__self__:
                        args.cls_type = cls_type
                        args.bound = bound
                        return args

    async def create(self, target, *args, **kwargs):
        impl = self.impl.__func__
        call = impl(target, *args, **kwargs)
        return await call if inspect.iscoroutinefunction(impl) else call

    def register(self, adapters):
        if self.lookup not in adapters.lookups:
            adapters["generic_index"] = collections.defaultdict(list)
            adapters.lookups[self.lookup] = True
        adapters["generic_index"][self.bound].insert(0, self)

    @staticmethod
    def lookup(adapters, target):
        # find generic adapters
        for base in inspect.getmro(target):
            if base in adapters["generic_index"]:
                yield from adapters["generic_index"][base]


class Adapters(dict, AdaptersImpl):
    def __init__(self):
        super().__init__()
        self.lookups = {}

    def register(self, *impls, frame=None):
        frame = frame or sys._getframe(1)
        for impl in impls:
            adapter = Adapter(impl, frame=frame)
            adapter.register(self)


def get_annotations(impl, *, frame=None):
    args = util.adict()
    args.hints = typing.get_type_hints(
        impl, frame.f_globals if frame else None, frame.f_locals if frame else None
    )
    args.spec = inspect.getfullargspec(impl)
    return args


def extract_optional_type(hint):
    if typing_inspect.is_optional_type(hint):
        none = type(None)
        for h in hint.__args__:
            if h is not none:
                return h
    return hint


def collect_defaults(spec):
    defaults = {
        k: v
        for k, v in itertools.chain(
            zip(reversed(spec.args or []), reversed(spec.defaults or [])),
            (spec.kwonlydefaults or {}).items(),
        )
    }
    return defaults


# our default adapters
buvar_adapters = contextvars.ContextVar(__name__)
buvar_adapters.set(Adapters())


def register(*impls):
    adapters = buvar_adapters.get()
    adapters.register(*impls, frame=sys._getframe(1))


async def nject(*targets, **dependencies):
    adapters = buvar_adapters.get()
    return await adapters.nject(*targets, **dependencies)
