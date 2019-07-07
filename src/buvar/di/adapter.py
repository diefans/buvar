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


@attr.s(auto_attribs=True)
class Adapter:
    func: typing.Callable
    spec: inspect.FullArgSpec
    frame: typing.Any
    owner: typing.Optional[typing.Type]
    name: typing.Optional[str]
    implements: typing.Type
    defaults: typing.Dict[str, typing.Any]

    @property
    def hints(self):
        if inspect.isfunction(self.func):
            if self.owner is not None:
                frame = self.frame.f_back.f_back
            else:
                frame = self.frame.f_back
        else:  # if inspect.isclass(self.func):
            frame = self.frame.f_back.f_back

        f_locals = dict(frame.f_locals)
        if isinstance(self.implements, str) and self.implements not in f_locals:
            f_locals[self.implements] = self.owner
        hints = typing.get_type_hints(
            self.func.__init__ if inspect.isclass(self.func) else self.func,
            frame.f_globals,
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
        if self.owner is not None:
            func = functools.partial(self.func, self.owner)
        else:
            func = self.func
        if inspect.iscoroutinefunction(self.func):
            adapted = await func(*args, **kwargs)
        else:
            adapted = func(*args, **kwargs)
        return adapted


adapters: typing.Dict[type, typing.List[Adapter]] = collections.defaultdict(list)
