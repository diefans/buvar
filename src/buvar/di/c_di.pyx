# cython: language_level=3
from ..components.c_components cimport Components, ComponentLookupError
from buvar import context


missing = object()


cdef class ResolveError(Exception):
    pass


cdef _get_name_or_default(cmps, target, name=None):
    # find in components
    if name is not None:
        try:
            component = cmps.get(target, name=name)
            return component
        except ComponentLookupError:
            pass

    component = cmps.get(target, name=None)
    return component


cdef prepare_components(tuple targets, dict dependencies):
    # create components
    cdef Components cmps = Components()
    cdef list stack

    # add default unnamed dependencies
    # every non-default argument of the same type gets its value
    # XXX is this good?
    for name, dep in dependencies.items():
        cmps.add(dep)

    cdef Components current_context = context.current_context()

    # add current context
    if not current_context:
        stack = []
    else:
        stack = current_context.stack
    cmps = cmps.push(*stack)

    # add default named dependencies
    cmps = cmps.push()
    for name, dep in dependencies.items():
        cmps.add(dep, name=name)

    return cmps


cdef class AdaptersImpl:
    async def nject(self, *targets, **dependencies):
        """Resolve all dependencies and return the created component."""

        cdef tuple _targets = targets

         # create components
        cdef Components cmps = prepare_components(_targets, dependencies)        # create components
        # find the proper components to instantiate that class
        cdef list injected = [
            await self.resolve_adapter(cmps, target, name=name)
            for name, target in ((None, target) for target in targets)
        ]
        if len(targets) == 1:
            return injected[0]
        return injected

    def get_possible_adapters(self, target):
        for lookup in self.lookups:
            yield from lookup(self, target)

    async def resolve_adapter(self, cmps, target, *, name=None, default=missing):
        # find in components
        try:
            component = _get_name_or_default(cmps, target, name)
            return component
        except ComponentLookupError:
            pass

        cdef list resolve_errors = []
        possible_adapters = self.get_possible_adapters(target)
        cdef dict adapter_args

        adptr = None
        for adptr in possible_adapters:
            try:
                adapter_args = {
                    name: await self.resolve_adapter(
                        cmps, dependency_target, name=name, default=default
                    )
                    for name, dependency_target, default in adptr.args
                }
            except ResolveError as ex:
                # try next adapter
                resolve_errors.append(ex)
            else:
                component = await adptr.create(target, **adapter_args)
                # we do not use the name
                cmps.add(component)
                return component

        if default is not missing:
            return default

        # have we tried at least one adapter
        if adptr is None:
            raise ResolveError("No possible adapter found", target, [])
        raise ResolveError("No adapter dependencies found", target, resolve_errors)
