import pytest


@pytest.fixture
def event_loop(event_loop):
    from buvar import context, components

    cmps = components.Components()
    context.set_task_factory(cmps, loop=event_loop)
    return event_loop


@pytest.fixture(params=['resolve', 'c_resolve'])
def nject(request):
    if request.param == 'resolve':
        from buvar.di import resolve
        yield resolve.nject
    else:
        try:
            from buvar.di import c_resolve as resolve
            yield resolve.nject         # noqa: I1101
        except ImportError:
            pytest.skip(f'C extension {request.param} not available.')
            return


@pytest.mark.asyncio
async def test_di(nject):
    from buvar import context, di

    class Foo(dict):
        def __init__(self, name=None):
            super().__init__(name=name, foo=True)

    @di.register
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

    @di.register
    async def baz_adapter(
        bar: Bar,
        bam: Foo = 1,
        bim: Bim = 'default',
        *,
        bum: Bum,
        foo: Foo = None
    ) -> Baz:
        return Baz(foo=foo, bam=bam, bim=bim, bar=bar, bum=bum)

    context.add(Foo())
    context.add(Foo(name='bar'), name='bar')

    baz, bum = await nject(Baz, Bum, bum=Bum())
    assert isinstance(baz, Baz)
    assert baz == {
        'baz': True,
        'bam': {'foo': True, 'name': None},
        'foo': {'foo': True, 'name': None},
        'bim': 'default',
        'bum': {'bum': True},
        'bar': {'bar': True, 'foo': {'foo': True, 'name':  'bar'}},
    }
    assert bum == {'bum': True}
