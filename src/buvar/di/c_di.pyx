# cython: language_level=3
from ..components cimport c_components as components

import sys
import collections
import functools
import inspect
import itertools
import typing

import typing_inspect

from buvar import context

from .. import util
# from ..components import c_components as components

missing = object()


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


class Adapter:
    def __init__(
        self,
        func,
        args,
        locals,
        globals,
        owner,
        name,
        implements,
        defaults,
    ):
        self.func = func
        self.args = args
        self.locals = locals
        self.globals = globals
        self.owner = owner
        self.name = name
        self.implements = implements
        self.defaults = defaults

    def get_hints(self):
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
        hints = self.get_hints()
        annotations = {
            arg: _extract_optional_type(hints[arg])
            for arg in self.args
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


cdef prepare_components(tuple targets, dict dependencies):
    # create components
    cdef components.Components cmps = components.Components()

    # add default unnamed dependencies
    # every non-default argument of the same type gets its value
    # XXX is this good?
    for name, dep in dependencies.items():
        cmps.add(dep)

    cdef components.Components current_context = context.current_context()

    # add current context
    cmps = cmps.push(*current_context.stack)

    # add default named dependencies
    cmps = cmps.push()
    for name, dep in dependencies.items():
        cmps.add(dep, name=name)

    return cmps


cdef class Adapters:
    cdef dict _index
    def __init__(self):
        self._index = {}

    @property
    def index(self):
        return self._index

    cpdef add(self, target, adapter):
        if target in self._index:
            self._index[target].append(adapter)
        else:
            self._index[target] = [adapter]

    def adapter_classmethod(self, func):
        """Register a classmethod to adapt its arguments into its return type."""

        class adapter:
            def __init__(deco, func):
                frame = sys._getframe(1)
                spec = inspect.getfullargspec(func)
                # remove cls arg
                spec.args.pop(0)
                implements = spec.annotations["return"]
                # all arguments must be annotated
                assert_annotated(spec)

                args = spec.args + spec.kwonlyargs

                deco.adapter = Adapter(
                    func=func,
                    args=args,
                    locals=frame.f_locals,
                    globals=frame.f_globals,
                    owner=None,
                    name=None,
                    defaults=collect_defaults(spec),
                    implements=implements,
                )
                self.add(implements, deco.adapter)

            def __set_name__(deco, owner, name):
                deco.adapter.owner = owner
                deco.adapter.name = name

                try:
                    hints = deco.adapter.get_hints()
                    deco.adapter.implements = hints["return"]
                    self.add(hints["return"], deco.adapter)
                except NameError:
                    pass

            def __get__(deco, instance, owner=None):
                if owner is None:
                    owner = type(instance)
                return functools.partial(deco.adapter.func, owner)

        return adapter(func)

    def adapter(self, func):
        """Register a class or function to adapt arguments either into its
        class or return type"""
        frame = sys._getframe(0)
        spec = inspect.getfullargspec(func)
        # remove self arg
        if inspect.isclass(func):
            spec.args.pop(0)
            implements = func
        else:
            implements = spec.annotations["return"]
        # all arguments must be annotated
        assert_annotated(spec)

        args = spec.args + spec.kwonlyargs
        adapter = Adapter(
            func=func,
            args=args,
            locals=frame.f_locals,
            globals=frame.f_globals,
            owner=None,
            name=None,
            defaults=collect_defaults(spec),
            implements=implements,
        )
        self.add(implements, adapter)
        return func

    async def nject(self, *targets, **dependencies):
        """Resolve all dependencies and return the created component."""

        # create components
        cmps = prepare_components(targets, dependencies)

        # find the proper components to instantiate that class
        injected = [
            await self.resolve_adapter(cmps, target, name=name)
            for name, target in ((None, target) for target in targets)
        ]
        if len(targets) == 1:
            return injected[0]
        return injected

    def find_string_target_adapters(self, target):
        name = target.__name__
        adapter_list = []

        # search for string and match
        string_adapters = self._index.get(name)
        # find target name in string adapter types and find target in adapter
        if string_adapters:
            for adptr in string_adapters:
                hints = adptr.get_hints()
                if hints["return"] is target:
                    adapter_list.append(adptr)
        return adapter_list

    async def resolve_adapter(self, cmps, target, *, name=None, default=missing):
        # find in components
        try:
            component = _get_name_or_default(cmps, target, name)
            return component
        except components.ComponentLookupError:
            pass

        # try to adapt
        possible_adapters = (
            self._index.get(target) or []
        ) + self.find_string_target_adapters(target)

        resolve_errors = []
        if possible_adapters is None:
            if default is missing:
                raise ResolveError("No possible adapter found", target, resolve_errors)
            return default

        for adptr in possible_adapters:
            try:
                adapter_args = {
                    name: await self.resolve_adapter(
                        cmps,
                        dependency_target,
                        name=name,
                        default=adptr.defaults.get(name, missing),
                    )
                    for name, dependency_target in adptr.annotations.items()
                }
            except ResolveError as ex:
                # try next adapter
                resolve_errors.append(ex)
            else:
                component = await adptr.create(**adapter_args)
                # we do not use the name
                cmps.add(component)
                return component
        if default is missing:
            raise ResolveError("No adapter dependencies found", target, resolve_errors)
        return default


cdef _get_name_or_default(components.Components cmps, object target, name=None):
    # find in components
    if name is not None:
        try:
            component = cmps.get(target, name=name)
            return component
        except components.ComponentLookupError:
            pass

    component = cmps.get(target, name=None)
    return component
