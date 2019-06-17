"""Dependency injection."""
import collections
import inspect
import itertools
import typing

import attr


class ResolveError(Exception):
    pass


@attr.s(auto_attribs=True)
class Adapter:
    callable: typing.Callable
    annotations: typing.Dict[str, typing.Any]
    defaults: typing.Dict[str, typing.Any]

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
            # routine needs to have a return annotaion
            if 'return' not in adapter.__annotations__:
                raise TypeError('Return type annoation missing', adapter)
            target = adapter.__annotations__['return']
            spec = inspect.getfullargspec(adapter)
        elif inspect.isclass(adapter):
            target = adapter
            spec = inspect.getfullargspec(adapter)
            # remove self
            spec.args.pop(0)
        else:
            raise TypeError('Expecting a routine or a class', adapter)

        # all spec must be annotated
        annotations = {
            arg: spec.annotations[arg]
            for arg in itertools.chain(
                spec.args,
                spec.kwonlyargs
            )
        }
        defaults = dict(
            itertools.chain(
                zip(
                    reversed(spec.args or []),
                    reversed(spec.defaults or []),
                ),
                (spec.kwonlydefaults or {}).items(),
            )
        )

        adapter_spec = cls(
            callable=adapter,
            annotations=annotations,
            defaults=defaults,
        )
        adapters[target].append(adapter_spec)

        return adapter


adapters: typing.Dict[
    type,
    typing.List[Adapter]
] = collections.defaultdict(list)


register = Adapter.register


try:
    # gains over 100% speed up
    from .c_resolve import nject
except ImportError:
    from .resolve import nject      # noqa: W0611
