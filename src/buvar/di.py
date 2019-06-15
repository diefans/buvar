"""Dependency injection."""
import collections
import inspect
import itertools
import typing

import attr

from buvar import components


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


def nject(*targets, **dependencies):
    from buvar import context

    # create components
    cmps = components.Components()

    # add default unnamed dependencies
    for name, dep in dependencies.items():
        cmps.add(dep)

    # add current context
    cmps.push(context.current_context().index)

    # add default named dependencies
    cmps.push()
    for name, dep in dependencies.items():
        cmps.add(dep, name=name)

    # find the proper components to instantiate that class
    for name, target in ((None, target) for target in targets):
        yield resolve_adapter(cmps, target, name=name)


def resolve_adapter(cmps, target, *, name=None, default=missing):
    # find in components
    try:
        component = _get_name_or_default(cmps, target, name)
        return component
    except components.ComponentLookupError:
        pass

    # try to adapt
    possible_adapters = adapters.get(target)
    if possible_adapters is None:
        if default is missing:
            raise ResolveError('Adapter not found', target)
        return default

    for adapter in possible_adapters:
        annotations = {
            arg: adapter.spec.annotations[arg]
            for arg in itertools.chain(
                adapter.spec.args,
                adapter.spec.kwonlyargs
            )
        }
        defaults = dict(
            itertools.chain(
                zip(
                    reversed(adapter.spec.args or []),
                    reversed(adapter.spec.defaults or [])
                ),
                (adapter.spec.kwonlydefaults or {}).items()
            )
        )
        try:
            adapter_args = {
                name: resolve_adapter(
                    cmps,
                    dependency_target,
                    name=name,
                    default=defaults.get(name, missing)
                )
                for name, dependency_target in annotations.items()
            }
        except ResolveError:
            # try next adapter
            pass
        else:
            component = adapter.create(**adapter_args)
            cmps.add(component)
            return component
    if default is missing:
        raise ResolveError('Adapter dependencies not found', target)
    return default


def _get_name_or_default(cmps, target, name=None):
    # find in components
    if name is not None:
        try:
            component = cmps.get(target, name=name)
            return component
        except components.ComponentLookupError:
            pass

    component = cmps.get(target, name=None)
    return component
