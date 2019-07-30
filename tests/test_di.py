from __future__ import annotations

import pytest


@pytest.fixture
def event_loop(event_loop):
    from buvar import context, components

    cmps = components.Components()
    context.set_task_factory(cmps, loop=event_loop)
    return event_loop


@pytest.mark.benchmark(group="nject")
def test_di_benchmark_empty_async(event_loop, benchmark):
    from buvar import context

    class Foo(dict):
        def __init__(self, name=None):
            super().__init__(name=name, foo=True)

    class Bar(dict):
        def __init__(self, bar: Foo):
            super().__init__(foo=bar, bar=True)

    async def test():
        context.add(Foo())
        context.add(Foo(name="bar"), name="bar")

    def bench():
        event_loop.run_until_complete(test())

    benchmark(bench)


@pytest.mark.benchmark(group="nject")
def test_di_nject(event_loop, benchmark):
    from buvar import context, di

    adapters = di.Adapters()

    class Foo(dict):
        def __init__(self, name=None):
            super().__init__(name=name, foo=True)

    @adapters.adapter
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

    @adapters.adapter
    async def baz_adapter(
        bar: Bar, bam: Foo = 1, bim: Bim = "default", *, bum: Bum, foo: Foo = None
    ) -> Baz:
        return Baz(foo=foo, bam=bam, bim=bim, bar=bar, bum=bum)

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


@pytest.mark.asyncio
async def test_di_adapter():
    from buvar import di

    adapters = di.Adapters()

    class Bar:
        @adapters.adapter_classmethod
        def adapt(cls) -> Bar:
            assert cls == Bar
            return cls()

    @adapters.adapter
    class Foo:
        def __init__(self, bar: Bar):
            self.bar = bar

        @adapters.adapter_classmethod
        def adapt(cls, bar: Bar) -> Foo:
            return cls(bar)

    @adapters.adapter
    def adapt(bar: Bar) -> Foo:
        return Foo(bar)

    bar = await adapters.nject(Bar)
    foo = await adapters.nject(Foo)
    assert set(adapters.index) == {"Foo", Foo, "Bar", Bar}


@pytest.mark.benchmark(group="readme")
def test_readme(event_loop, benchmark):
    from buvar import di

    adapters = di.Adapters()

    class Bar:
        pass

    class Foo:
        def __init__(self, bar: Bar = None):
            self.bar = bar

        @adapters.adapter_classmethod
        async def adapt_classmethod(cls, baz: str) -> Foo:
            return Foo()

    @adapters.adapter
    async def adapt(bar: Bar) -> Foo:
        foo = Foo(bar)
        return foo

    async def test():
        foo = await adapters.nject(Foo, baz="baz")
        assert foo.bar is None

        bar = Bar()
        foo = await adapters.nject(Foo, bar=bar)
        assert foo.bar is bar

    def bench():
        event_loop.run_until_complete(test())

    benchmark(bench)
