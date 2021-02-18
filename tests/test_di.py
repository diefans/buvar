import pytest


@pytest.fixture
def adapters():
    from buvar.di import Adapters

    return Adapters()


def test_adapters_register_generic_factory(adapters):
    import typing

    FooType = typing.TypeVar("FooType", bound="Foo")

    class Foo:
        @classmethod
        async def generic_adapt(cls: typing.Type[FooType]) -> FooType:
            return cls()

    adapters.register(Foo.generic_adapt)
    assert [Foo.generic_adapt] == [
        adapter.impl for adapter in adapters["generic_index"][Foo]
    ]


def test_adapters_register_class(adapters):
    class Bar:
        def __init__(self):
            ...

    adapters.register(Bar)
    assert [Bar] == [adapter.impl for adapter in adapters["index"][Bar]]


def test_adapters_register_classmethod(adapters):
    class Bar:
        @classmethod
        def adapt(cls) -> "Bar":
            return cls()

    adapters.register(Bar.adapt)
    assert [Bar.adapt] == [adapter.impl for adapter in adapters["index"][Bar]]


def test_adapters_register_func(adapters):
    class Bar:
        ...

    def foo_adapter() -> Bar:
        return Bar()

    adapters.register(foo_adapter)
    assert [foo_adapter] == [adapter.impl for adapter in adapters["index"][Bar]]


@pytest.mark.asyncio
async def test_nject_generic_factory(adapters):
    import typing

    FooType = typing.TypeVar("FooType", bound="Foo")

    class Foo:
        @classmethod
        async def adapt(cls: typing.Type[FooType]) -> FooType:
            return cls()

    class Bar(Foo):
        pass

    adapters.register(Foo.adapt)

    bar = await adapters.nject(Bar)
    assert isinstance(bar, Bar)


@pytest.mark.asyncio
async def test_nject_classmethod(adapters):
    class Foo:
        @classmethod
        async def adapt(cls) -> "Foo":
            return cls()

    adapters.register(Foo.adapt)

    foo = await adapters.nject(Foo)
    assert isinstance(foo, Foo)


@pytest.mark.asyncio
async def test_nject_class(adapters):
    class Foo:
        ...

    adapters.register(Foo)

    foo = await adapters.nject(Foo)
    assert isinstance(foo, Foo)


@pytest.mark.asyncio
async def test_nject_func(adapters):
    class Foo:
        ...

    async def adapt_foo() -> Foo:
        return Foo()

    adapters.register(adapt_foo)

    foo = await adapters.nject(Foo)
    assert isinstance(foo, Foo)


@pytest.mark.asyncio
async def test_nject_optional(adapters):
    import typing

    class Bar:
        ...

    class Foo:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    async def adapt_foo(bar: typing.Optional[Bar] = None) -> Foo:
        return Foo(bar=bar)

    adapters.register(adapt_foo)

    foo = await adapters.nject(Foo)
    assert foo.kwargs["bar"] is None


@pytest.mark.benchmark(group="nject")
def test_di_nject(event_loop, benchmark, adapters):
    from buvar import context

    class Foo(dict):
        def __init__(self, name=None):
            super().__init__(name=name, foo=True)

    class Bar(dict):
        def __init__(self, bar: Foo):
            super().__init__(foo=bar, bar=True)

    class Baz(dict):
        def __init__(self, **kwargs):
            super().__init__(baz=True, **kwargs)

    class Bim:
        pass

    class Bum(dict):
        def __init__(self):
            super().__init__(bum=True)

    async def baz_adapter(
        bar: Bar, bam: Foo = 1, bim: Bim = "default", *, bum: Bum, foo: Foo = None
    ) -> Baz:
        return Baz(foo=foo, bam=bam, bim=bim, bar=bar, bum=bum)

    adapters.register(Bar, baz_adapter)

    async def test():
        context.add(Foo())
        context.add(Foo(name="bar"), name="bar")

        baz, bum = await adapters.nject(Baz, Bum, bum=Bum())
        assert isinstance(baz, Baz)
        assert baz == {
            "baz": True,
            "bam": {"foo": True, "name": None},
            "foo": {"foo": True, "name": None},
            "bim": "default",
            "bum": {"bum": True},
            "bar": {"bar": True, "foo": {"foo": True, "name": "bar"}},
        }
        assert bum == {"bum": True}

    def bench():
        event_loop.run_until_complete(test())

    benchmark(bench)


@pytest.mark.benchmark(group="nject_2")
def test_nject_2(event_loop, benchmark, adapters):
    class Bar:
        pass

    class Foo:
        def __init__(self, bar: Bar = None):
            self.bar = bar

        @classmethod
        async def adapt_classmethod(cls, baz: str) -> "Foo":
            return Foo()

    async def adapt(bar: Bar) -> Foo:
        foo = Foo(bar)
        return foo

    adapters.register(Foo.adapt_classmethod, adapt)

    async def test():
        foo = await adapters.nject(Foo, baz="baz")
        assert foo.bar is None

        bar = Bar()
        foo = await adapters.nject(Foo, bar=bar)
        assert foo.bar is bar

    def bench():
        event_loop.run_until_complete(test())

    benchmark(bench)


@pytest.mark.asyncio
async def test_abc_meta_derived(adapters):
    import abc

    class Foo(abc.ABC):
        ...

    class Bar(Foo):
        ...

    adapters.register(Bar)

    bar = await adapters.nject(Bar)
    assert isinstance(bar, Bar)


@pytest.mark.asyncio
async def test_adapter_string_return(adapters):
    class Foo:
        @classmethod
        def adapt(cls, str: str) -> "Foo":
            return cls()

    adapters.register(Foo)

    foo = await adapters.nject(Foo)
    assert isinstance(foo, Foo)
