from buvar import components, context
from .exc import missing, ResolveError


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


class AdaptersImpl:
    async def nject(self, *targets, **dependencies):
        """Resolve all dependencies and return the created component."""
        # create components
        cmps = components.Components()

        # add default unnamed dependencies
        # every non-default argument of the same type gets its value
        # XXX is this good?
        for dep in dependencies.values():
            cmps.add(dep)

        # add current context
        current_context = context.current_context()
        stack = current_context.stack if current_context else []
        cmps = cmps.push(*stack)

        # add default named dependencies
        cmps = cmps.push()
        for name, dep in dependencies.items():
            cmps.add(dep, name=name)

        # find the proper components to instantiate that class
        injected = [
            await self.resolve_adapter(cmps, target, name=name)
            for name, target in ((None, target) for target in targets)
        ]
        if len(targets) == 1:
            return injected[0]
        return injected

    async def resolve_adapter(self, cmps, target, *, name=None, default=missing):
        # find in components
        try:
            component = _get_name_or_default(cmps, target, name)
            return component
        except components.ComponentLookupError:
            pass

        resolve_errors = []

        for adapter in self.lookup(target):
            try:
                adapter_args = {
                    param.name: await self.resolve_adapter(
                        cmps,
                        param.annotation,
                        name=param.name,
                        default=param.default,
                    )
                    for param in adapter.parameters.values()
                }
            except ResolveError as ex:
                # try next adapter
                resolve_errors.append(ex)
            else:
                component = await adapter.create(target, **adapter_args)
                # we do not use the name
                cmps.add(component)
                return component

        if default is not missing:
            return default

        if resolve_errors:
            raise ResolveError("No adapter dependencies found", target, resolve_errors)
        raise ResolveError("No possible adapter found", target, [])
