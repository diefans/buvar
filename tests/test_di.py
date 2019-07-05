from __future__ import annotations

import pytest


@pytest.fixture
def event_loop(event_loop):
    from buvar import context, components

    cmps = components.Components()
    context.set_task_factory(cmps, loop=event_loop)
    return event_loop


@pytest.fixture(params=["resolve", "c_resolve"])
def nject(request):
    if request.param == "resolve":
        from buvar.di import resolve

        yield resolve.nject
    else:
        try:
            from buvar.di import c_resolve as resolve

            yield resolve.nject  # noqa: I1101
        except ImportError:
            pytest.skip(f"C extension {request.param} not available.")
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
        bar: Bar, bam: Foo = 1, bim: Bim = "default", *, bum: Bum, foo: Foo = None
    ) -> Baz:
        return Baz(foo=foo, bam=bam, bim=bim, bar=bar, bum=bum)

    context.add(Foo())
    context.add(Foo(name="bar"), name="bar")

    baz, bum = await nject(Baz, Bum, bum=Bum())
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


def test_di_register():
    import attr
    import inspect
    import typing
    import collections
    import itertools
    import functools

    adapters: typing.Dict[type, typing.List[Adapter]] = collections.defaultdict(list)

    @attr.s(auto_attribs=True)
    class Adapter:
        func: typing.Callable
        spec: inspect.FullArgSpec
        globals: typing.Dict[str, typing.Any]
        locals: typing.Dict[str, typing.Any]
        owner: typing.Optional[typing.Type]
        name: typing.Optional[str]
        implements: typing.Type
        defaults: typing.Dict[str, typing.Any]

        @property
        def hints(self):
            if isinstance(self.implements, str) and self.implements not in self.locals:
                locals = dict(self.locals)
                locals[self.implements] = self.owner
            hints = typing.get_type_hints(self.func, self.globals, locals)
            return hints

    class register:
        """Register a class, function or method to adapt arguments into something else.

        >>> class Bar:
        ...     pass

        >>> @register
        ... class Foo:
        ...     def __init__(self, bar: Bar):
        ...         self.bar = bar

        >>>     @register
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
            frame = inspect.currentframe().f_back.f_back
            spec = inspect.getfullargspec(func)

            implements = func if inspect.isclass(func) else spec.annotations["return"]

            # all none defaults must be annotated
            defaults = dict(
                itertools.chain(
                    zip(reversed(spec.args or []), reversed(spec.defaults or [])),
                    (spec.kwonlydefaults or {}).items(),
                )
            )

            self.adapter = Adapter(
                func=func,
                spec=spec,
                globals=frame.f_globals,
                locals=frame.f_locals,
                owner=None,
                name=None,
                defaults=defaults,
                implements=implements,
            )
            adapters[implements].append(self.adapter)

        def __set_name__(self, owner, name):
            frame = inspect.currentframe()
            self.adapter.owner = owner
            self.adapter.name = name
            try:
                hints = self.adapter.hints
                self.adapter.implements = hints["return"]
                adapters[hints["return"]].append(self.adapter)
            except NameError:
                pass

        def __get__(self, instance, owner=None):
            if owner is None:
                owner = type(instance)
            return functools.partial(self.adapter.func, owner)

        def __call__(self, *args, **kwargs):
            return self.adapter.func(*args, **kwargs)

    class Bar:
        pass

    @register
    class Foo:
        def __init__(self, bar: Bar):
            self.bar = bar

        @register
        def adapt(cls, bar: Bar) -> Foo:
            return cls(bar)

    @register
    def adapt(bar: Bar) -> Foo:
        return Foo(bar)
