import pytest


@pytest.fixture
def adapters():
    from buvar import di

    return di.Adapters()


@pytest.fixture
def Foo():
    import dataclasses as dc

    @dc.dataclass
    class Foo:
        bim: str
        bam: int = 123
        baz: bool = False

        @classmethod
        def adapt_children(cls) -> "Foo":
            return cls(bim=cls.__name__)

    return Foo


@pytest.fixture
def Bar(Foo):
    import dataclasses as dc
    import typing as t

    @dc.dataclass
    class Bar(Foo):
        @classmethod
        def adapt(cls, bim: str) -> t.Optional["Bar"]:
            return Bar(bim="bam")

    return Bar


@pytest.mark.asyncio
async def test_create_adapter_callable(adapters, Foo, Bar):
    import typing as t

    async def adapt_list_of_bar() -> t.List[Bar]:
        return [Bar(bim="foo")]

    adapters.register(adapt_list_of_bar)
    adapters.register(Bar)
    adapters.register(Bar.adapt)

    assert len(list(adapters.lookup(Foo))) == 1
    assert list(adapters.lookup(Bar))
    assert list(adapters.lookup(t.Optional[Foo]))
    assert list(adapters.lookup(t.List[Foo]))

    assert await adapters.nject(t.List[Foo])
    assert await adapters.nject(t.Optional[Bar], bim="foo")
    assert isinstance(await adapters.nject(Foo, bim="foo"), Foo)
    assert isinstance(await adapters.nject(Bar, bim="bar"), Bar)


@pytest.mark.benchmark(group="lookup")
def test_adapters_lookup_benchmark(adapters, Foo, Bar, benchmark):
    import typing as t

    async def adapt_list_of_bar() -> t.List[Bar]:
        return [Bar(bim="foo")]

    adapters.register(adapt_list_of_bar)
    adapters.register(Bar)
    adapters.register(Bar.adapt)

    def lookup():
        assert len(list(adapters.lookup(Foo))) == 1
        assert list(adapters.lookup(Bar))
        assert list(adapters.lookup(t.Optional[Foo]))
        assert list(adapters.lookup(t.List[Foo]))

    benchmark(lookup)


@pytest.mark.asyncio
async def test_create_adapter_inheritance(adapters):

    class Baz:
        ...

    class Foo:
        def __init__(self, bim: str):
            self.bim = bim

        @classmethod
        def adapt_children(cls) -> "Foo":
            return cls(bim=cls)

        @classmethod
        def adapt_other(cls) -> Baz:
            baz = Baz()
            baz.adapter = cls
            return baz

    class Bar(Foo):
        ...

    adapters.register(Foo.adapt_children, Foo.adapt_other)

    bar = await adapters.nject(Bar)
    assert bar.bim == Bar
    bar = await adapters.nject(Bar)
    assert bar.bim == Bar

    baz = await adapters.nject(Baz)
    assert baz.adapter == Foo
