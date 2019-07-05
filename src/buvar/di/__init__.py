"""Dependency injection."""
import collections
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


@attr.s(auto_attribs=True)
class Adapter:
    callable: typing.Callable
    spec: inspect.FullArgSpec
    defaults: typing.Dict[str, typing.Any]
    globals: typing.Dict[str, typing.Any]
    locals: typing.Dict[str, typing.Any]

    @util.reify
    def hints(self):
        hints = typing.get_type_hints(
            self.callable.__func__
            if isinstance(self.callable, classmethod)
            else self.callable.__init__
            if inspect.isclass(self.callable)
            else self.callable,
            self.globals,
            self.locals,
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
        if inspect.iscoroutinefunction(self.callable):
            adapted = await self.callable(*args, **kwargs)
        else:
            adapted = self.callable(*args, **kwargs)
        return adapted

    @classmethod
    def register(cls, adapter: typing.Callable):
        """Register an adapter for later lookup."""
        # Inspect param types of class or fun.
        if inspect.isroutine(adapter):
            # __func__ indicates a classmethod
            if isinstance(adapter, classmethod):
                spec = inspect.getfullargspec(adapter.__func__)
                a_source = adapter.__func__.__annotations__
                # remove cls
                spec.args.pop(0)
            else:
                spec = inspect.getfullargspec(adapter)
                a_source = adapter.__annotations__

            # routine needs to have a return annotaion
            if "return" not in a_source:
                raise TypeError("Return type annoation missing", adapter)
            target = a_source["return"]
        elif inspect.isclass(adapter):
            target = adapter
            spec = inspect.getfullargspec(adapter)
            # remove self
            spec.args.pop(0)
        else:
            raise TypeError("Expecting a routine or a class", adapter)

        # all spec must be annotated
        defaults = dict(
            itertools.chain(
                zip(reversed(spec.args or []), reversed(spec.defaults or [])),
                (spec.kwonlydefaults or {}).items(),
            )
        )
        frame = inspect.currentframe().f_back
        frame_globals = frame.f_globals
        frame_locals = frame.f_locals

        adapter_spec = cls(
            callable=adapter,
            spec=spec,
            defaults=defaults,
            globals=frame_globals,
            locals=frame_locals,
        )
        adapters[target].append(adapter_spec)

        return adapter


adapters: typing.Dict[type, typing.List[Adapter]] = collections.defaultdict(list)


register = Adapter.register


try:
    # gains over 100% speed up
    from .c_resolve import nject
except ImportError:
    from .resolve import nject  # noqa: W0611
