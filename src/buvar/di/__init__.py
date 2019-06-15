"""Dependency injection."""
import collections
import inspect
import typing

import attr


class ResolveError(Exception):
    pass


missing = object()


@attr.s(auto_attribs=True)
class Adapter:
    create: typing.Union[typing.Callable, type]
    spec: inspect.FullArgSpec


adapters: typing.Dict[
    type,
    typing.List[Adapter]
] = collections.defaultdict(list)


def register(adapter):
    # Inspect param types of class or fun.
    if inspect.isroutine(adapter):
        # routine needs to have a return annotaion
        if 'return' not in adapter.__annotations__:
            raise TypeError('Return type annoation missing', adapter)
        target = adapter.__annotations__['return']
        args = inspect.getfullargspec(adapter)
    elif inspect.isclass(adapter):
        target = adapter
        args = inspect.getfullargspec(adapter)
        # remove self
        args.args.pop(0)
    else:
        raise TypeError('Expecting a rountine or a class', adapter)

    # all args must be annotated

    adapters[target].append(Adapter(adapter, args))
    return adapter


try:
    # gains over 100% speed up
    from .c_resolve import nject
except ImportError:
    from .resolve import nject      # noqa: W0611
