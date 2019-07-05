import inspect

import typing_inspect

from . import ResolveError, adapters
from .. import components

missing = object()


async def nject(*targets, **dependencies):
    """Resolve all dependencies and return the created component."""
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
    injected = [
        await resolve_adapter(cmps, target, name=name)
        for name, target in ((None, target) for target in targets)
    ]
    if len(targets) == 1:
        return injected[0]
    return injected


def find_string_target_adapters(target):
    name = target.__name__

    # search for string and match
    string_adapters = adapters.get(name)
    # find name in adapter module
    if string_adapters:
        for adapter in string_adapters:
            if adapter.hints["return"] is target:
                yield adapter


async def resolve_adapter(cmps, target, *, name=None, default=missing):
    # find in components
    try:
        component = _get_name_or_default(cmps, target, name)
        return component
    except components.ComponentLookupError:
        pass

    # try to adapt
    possible_adapters = adapters.get(target) or list(
        find_string_target_adapters(target)
    )

    if possible_adapters is None:
        if default is missing:
            raise ResolveError("Adapter not found", target)
        return default

    for adapter in possible_adapters:
        try:
            adapter_args = {
                name: await resolve_adapter(
                    cmps,
                    dependency_target,
                    name=name,
                    default=adapter.defaults.get(name, missing),
                )
                for name, dependency_target in adapter.annotations.items()
            }
        except ResolveError:
            # try next adapter
            pass
        else:
            component = await adapter.create(**adapter_args)
            # we do not use the name
            cmps.add(component)
            return component
    if default is missing:
        raise ResolveError("Adapter dependencies not found", target)
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
