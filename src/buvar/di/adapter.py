import collections
import functools
import inspect
import itertools
import typing

import attr
import typing_inspect

from .. import util


class ResolveError(Exception):
    pass


def _extract_optional_type(hint):
    if typing_inspect.is_optional_type(hint):
        hint, _ = typing_inspect.get_args(hint)
        return hint
    return hint


def assert_annotated(spec):
    assert set(spec.args + spec.kwonlyargs).issubset(
        set(spec.annotations)
    ), "An adapter must annotate all of its arguments."


def collect_defaults(spec):
    defaults = dict(
        itertools.chain(
            zip(reversed(spec.args or []), reversed(spec.defaults or [])),
            (spec.kwonlydefaults or {}).items(),
        )
    )
    return defaults


@attr.s(auto_attribs=True)
class Adapter:
    func: typing.Callable
    spec: inspect.FullArgSpec
    # frame: typing.Any
    locals: typing.Dict[str, typing.Any]
    globals: typing.Dict[str, typing.Any]
    owner: typing.Optional[typing.Type]
    name: typing.Optional[str]
    implements: typing.Type
    defaults: typing.Dict[str, typing.Any]

    @classmethod
    def from_classmethod(cls, func):
        """Register a classmethod to adapt its arguments into its return type."""

        class adapter:
            def __init__(self, func):
                frame = inspect.currentframe()
                spec = inspect.getfullargspec(func)
                # remove cls arg
                spec.args.pop(0)
                implements = spec.annotations["return"]
                # all arguments must be annotated
                assert_annotated(spec)

                frame = frame.f_back.f_back.f_back
                self.adapter = cls(
                    func=func,
                    spec=spec,
                    locals=frame.f_locals,
                    globals=frame.f_globals,
                    owner=None,
                    name=None,
                    defaults=collect_defaults(spec),
                    implements=implements,
                )
                adapters[implements].append(self.adapter)

            def __set_name__(self, owner, name):
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

        return adapter(func)

    @classmethod
    def from_func(cls, func):
        """Register a class or function to adapt arguments either into its
        class or return type"""
        frame = inspect.currentframe()
        spec = inspect.getfullargspec(func)
        # remove self arg
        if inspect.isclass(func):
            spec.args.pop(0)
            implements = func
        else:
            implements = spec.annotations["return"]
        # all arguments must be annotated
        assert_annotated(spec)

        frame = frame.f_back
        adapter = cls(
            func=func,
            spec=spec,
            locals=frame.f_locals,
            globals=frame.f_globals,
            owner=None,
            name=None,
            defaults=collect_defaults(spec),
            implements=implements,
        )
        adapters[implements].append(adapter)
        return func

    @property
    def hints(self):
        f_locals = dict(self.locals)
        if isinstance(self.implements, str) and self.implements not in f_locals:
            f_locals[self.implements] = self.owner
        hints = typing.get_type_hints(
            self.func.__init__ if inspect.isclass(self.func) else self.func,
            self.globals,
            f_locals,
        )
        return hints

    @util.reify
    def annotations(self):
        hints = self.hints
        annotations = {
            arg: _extract_optional_type(hints[arg])
            for arg in itertools.chain(self.spec.args, self.spec.kwonlyargs)
        }

        return annotations

    async def create(self, *args, **kwargs):
        """Create the target instance."""
        func = functools.partial(self.func, self.owner) if self.owner else self.func
        if inspect.iscoroutinefunction(self.func):
            adapted = await func(*args, **kwargs)
        else:
            adapted = func(*args, **kwargs)
        return adapted


adapters: typing.Dict[type, typing.List[Adapter]] = collections.defaultdict(list)
