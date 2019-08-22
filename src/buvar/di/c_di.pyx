# cython: language_level=3
from ..components.c_components cimport Components, ComponentLookupError

import sys
import collections
import functools
import inspect
import itertools
import typing

# import typing_inspect

from buvar import context

from .. import util

missing = object()


class ResolveError(Exception):
    pass


cdef _extract_optional_type(hint):
    none = type(None)
    if (
        hint is typing.Union
        or isinstance(hint, typing._GenericAlias)
        and hint.__origin__ is typing.Union
    ):
        if none in hint.__args__ and len(hint.__args__) == 2:
            for h in hint.__args__:
                if h is not none:
                    return h
    return hint
    # if typing_inspect.is_optional_type(hint):
    #     hint, _ = typing_inspect.get_args(hint)
    #     return hint
    # return hint


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


cdef class Adapter:
    cdef func
    cdef list args
    cdef dict locals
    cdef dict globals
    cdef owner
    cdef name
    cdef object implements
    cdef dict defaults
    cdef _annotations

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
        self._annotations = None

    cdef get_hints(self):
        f_locals = dict(self.locals)
        if isinstance(self.implements, str) and self.implements not in f_locals:
            f_locals[self.implements] = self.owner
        hints = typing.get_type_hints(
            self.func.__init__ if isinstance(self.func, type) else self.func,
            self.globals,
            f_locals,
        )

        return hints

    cdef __annotations(self):
        if self._annotations is not None:
            return self._annotations

        cdef dict hints = self.get_hints()
        self._annotations = {
            arg: _extract_optional_type(hints[arg])
            for arg in self.args
        }

        return self._annotations

    @property
    def annotations(self):
        return self.__annotations()

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
    cdef Components cmps = Components()

    # add default unnamed dependencies
    # every non-default argument of the same type gets its value
    # XXX is this good?
    for name, dep in dependencies.items():
        cmps.add(dep)

    cdef Components current_context = context.current_context()

    # add current context
    cmps = cmps.push(*current_context.stack)

    # add default named dependencies
    cmps = cmps.push()
    for name, dep in dependencies.items():
        cmps.add(dep, name=name)

    return cmps


cdef class _adapter:
    cdef Adapters adapters
    cdef Adapter adapter

    def __init__(self, func, adapters):
        self.adapters = adapters
        frame = sys._getframe(1)
        spec = inspect.getfullargspec(func)
        # remove cls arg
        spec.args.pop(0)
        implements = spec.annotations["return"]
        # all arguments must be annotated
        assert_annotated(spec)

        args = spec.args + spec.kwonlyargs

        self.adapter = Adapter(
            func=func,
            args=args,
            locals=frame.f_locals,
            globals=frame.f_globals,
            owner=None,
            name=None,
            defaults=collect_defaults(spec),
            implements=implements,
        )
        adapters.add(implements, self.adapter)

    def __set_name__(self, owner, name):
        self.adapter.owner = owner
        self.adapter.name = name

        try:
            hints = self.adapter.get_hints()
            self.adapter.implements = hints["return"]
            self.adapters.add(hints["return"], self.adapter)
        except NameError:
            pass

    def __get__(self, instance, owner):
        if owner is None:
            owner = type(instance)
        return functools.partial(self.adapter.func, owner)


cdef class Adapters:
    cdef dict _index
    def __init__(self):
        self._index = {}

    @property
    def index(self):
        return self._index

    cdef _add(self, target, adapter):
        if target in self._index:
            self._index[target].append(adapter)
        else:
            self._index[target] = [adapter]

    def add(self, target, adapter):
        self._add(target, adapter)

    def adapter_classmethod(self, func):
        """Register a classmethod to adapt its arguments into its return type."""
        return _adapter(func, self)

    def adapter(self, func):
        """Register a class or function to adapt arguments either into its
        class or return type"""
        frame = sys._getframe(0)
        spec = inspect.getfullargspec(func)
        # remove self arg
        if isinstance(func, type):
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
        self._add(implements, adapter)
        return func

    async def nject(self, *targets, **dependencies):
        """Resolve all dependencies and return the created component."""
        cdef tuple _targets = targets

        # create components
        cdef Components cmps = prepare_components(_targets, dependencies)

        # find the proper components to instantiate that class
        cdef list injected = [
            await self.resolve_adapter(cmps, target, name=name)
            for name, target in ((None, target) for target in targets)
        ]
        if len(targets) == 1:
            return injected[0]
        return injected

    cdef _find_string_target_adapters(self, type target):
        cdef str name = target.__name__
        cdef list adapter_list = []

        # search for string and match
        cdef list string_adapters = self._index.get(name)
        cdef Adapter adptr
        # find target name in string adapter types and find target in adapter
        if string_adapters:
            for adptr in string_adapters:
                hints = adptr.get_hints()
                if hints["return"] is target:
                    adapter_list.append(adptr)
        return adapter_list

    async def resolve_adapter(self, Components cmps, object target, *, name=None, default=missing):
        cdef object component
        # find in components
        try:
            component = _get_name_or_default(cmps, target, name)
            return component
        except ComponentLookupError:
            pass

        # try to adapt
        cdef list possible_adapters = (
            self._index.get(target) or []
        ) + self._find_string_target_adapters(target)

        cdef list resolve_errors = []
        if possible_adapters is None:
            if default is missing:
                raise ResolveError("No possible adapter found", target, resolve_errors)
            return default
        cdef Adapter adptr
        cdef dict adapter_args
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
                cmps._add(component)
                return component
        if default is missing:
            raise ResolveError("No adapter dependencies found", target, resolve_errors)
        return default


cdef _get_name_or_default(Components cmps, object target, name=None):
    # find in components
    if name is not None:
        try:
            component = cmps._get(target, name=name)
            return component
        except ComponentLookupError:
            pass

    component = cmps._get(target, name=None)
    return component
