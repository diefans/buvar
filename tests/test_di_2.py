import collections
import inspect
import sys
import types
import typing

import pytest
import typing_inspect

from buvar import util

PY_36 = sys.version_info < (3, 7)


def get_annotations(impl, *, frame):
    args = util.adict()
    args.hints = typing.get_type_hints(
        impl, frame.f_globals if frame else None, frame.f_locals if frame else None
    )
    args.spec = inspect.getfullargspec(impl)
    return args


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
        print("impl", impl)
        self.impl = impl
        self.spec = spec
        self.hints = hints

    @classmethod
    def test_impl(cls, impl, *, frame):
        # TODO test for sane hints
        if callable(impl):
            return get_annotations(impl, frame=frame)

    @util.reify
    def target(self):
        return self.hints["return"]

    def register(self, adapters):
        adapters.index[self.target].insert(0, self)

    async def create(self, target, *args, **kwargs):
        ...


class ClassAdapter(Adapter):
    @util.reify
    def target(self):
        return self.impl

    @classmethod
    def test_impl(cls, impl, *, frame):
        if isinstance(impl, type):
            return super().test_impl(impl.__init__, frame=frame)


class ClassmethodAdapter(Adapter):
    @classmethod
    def test_impl(cls, impl, *, frame):
        if isinstance(impl, types.MethodType) and isinstance(impl.__self__, type):
            return super().test_impl(impl.__func__, frame=frame)


class GenericFactoryAdapter(ClassmethodAdapter):
    def __init__(self, impl, *, spec, hints, cls_type):
        self.impl = impl
        self.spec = spec
        self.hints = hints
        self.cls_type = cls_type

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

            if cls_type is target:
                bound = typing_inspect.get_bound(cls_type)
                if bound:
                    bound = getattr(bound, "_eval_type" if PY_36 else "_evaluate")(
                        frame.f_globals, frame.f_locals
                    )
                    if bound is impl.__self__:
                        args.cls_type = cls_type
                        return args

    def register(self, adapters):
        adapters.generic_index[self.target].insert(0, self)

    ...


class Adapters:
    def __init__(self):
        self.index: typing.Dict[type, typing.List[Adapter]] = collections.defaultdict(
            list
        )
        self.generic_index: typing.Dict[
            typing.Type, typing.List[Adapter]
        ] = collections.defaultdict(list)

    def register(self, impl):
        frame = sys._getframe(1)
        adapter = Adapter(impl, frame=frame)
        adapter.register(self)


@pytest.fixture
def adapters():
    return Adapters()


def test_adapters_register_generic_factory(adapters):
    FooType = typing.TypeVar("FooType", bound="Foo")

    class Foo:
        @classmethod
        async def generic_adapt(cls: typing.Type[FooType]) -> FooType:
            return cls()

    adapters.register(Foo.generic_adapt)
    assert [Foo.generic_adapt] == [
        adapter.impl for adapter in adapters.generic_index[FooType]
    ]


def test_adapters_register_class(adapters):
    class Bar:
        def __init__(self):
            ...

    adapters.register(Bar)
    assert [Bar] == [adapter.impl for adapter in adapters.index[Bar]]


def test_adapters_register_classmethod(adapters):
    class Bar:
        @classmethod
        def adapt(cls) -> "Bar":
            return cls()

    adapters.register(Bar.adapt)
    assert [Bar.adapt] == [adapter.impl for adapter in adapters.index[Bar]]


def test_adapters_register_func(adapters):
    class Bar:
        ...

    def foo_adapter() -> Bar:
        return Bar()

    adapters.register(foo_adapter)
    assert [foo_adapter] == [adapter.impl for adapter in adapters.index[Bar]]
