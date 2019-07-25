from buvar import context

from .. import di
from ..components import py_components as components

missing = object()


async def nject(*targets, **dependencies):
    """Resolve all dependencies and return the created component."""

    # create components
    cmps = components.Components()

    # add default unnamed dependencies
    # every non-default argument of the same type gets its value
    # XXX is this good?
    for name, dep in dependencies.items():
        cmps.add(dep)

    # add current context
    cmps = cmps.push(*context.current_context().stack)

    # add default named dependencies
    cmps = cmps.push()
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
    adapter_list = []

    # search for string and match
    string_adapters = di.adapters.get(name)
    # find target name in string adapter types and find target in adapter
    if string_adapters:
        for adptr in string_adapters:
            if adptr.hints["return"] is target:
                adapter_list.append(adptr)
    return adapter_list


async def resolve_adapter(cmps, target, *, name=None, default=missing):
    # find in components
    try:
        component = _get_name_or_default(cmps, target, name)
        return component
    except components.ComponentLookupError:
        pass

    # try to adapt
    possible_adapters = (di.adapters.get(target) or []) + find_string_target_adapters(
        target
    )

    resolve_errors = []
    if possible_adapters is None:
        if default is missing:
            raise di.ResolveError("No possible adapter found", target, resolve_errors)
        return default

    for adptr in possible_adapters:
        try:
            adapter_args = {
                name: await resolve_adapter(
                    cmps,
                    dependency_target,
                    name=name,
                    default=adptr.defaults.get(name, missing),
                )
                for name, dependency_target in adptr.annotations.items()
            }
        except di.ResolveError as ex:
            # try next adapter
            resolve_errors.append(ex)
        else:
            component = await adptr.create(**adapter_args)
            # we do not use the name
            cmps.add(component)
            return component
    if default is missing:
        raise di.ResolveError("No adapter dependencies found", target, resolve_errors)
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
