# cython: language_level=3
from ..components.c_components cimport Components, ComponentLookupError

import sys
import collections
import functools
import inspect
import itertools
import typing

import typing_inspect

from buvar import context

from .. import util

PY_36 = sys.version_info < (3, 7)

missing = object()


class ResolveError(Exception):
    pass


cdef _extract_optional_type(hint):
    if typing_inspect.is_optional_type(hint):
        none = type(None)
        for h in hint.__args__:
            if h is not none:
                return h
    return hint


class AdapterError(Exception):
    pass


def assert_annotated(spec):
    if not set(spec.args + spec.kwonlyargs).issubset(set(spec.annotations)):
        raise AdapterError("An adapter must annotate all of its arguments.", spec)


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
    cdef object implements
    cdef dict defaults
    cdef owner
    cdef str name
    cdef generic
    cdef _annotations

    def __init__(
        self,
        func,
        args,
        locals,
        globals,
        implements,
        defaults,
        owner=None,
        name=None,
        generic=False,
    ):
        self.func = func
        self.args = args
        self.locals = locals
        self.globals = globals
        self.owner = owner
        self.name = name
        self.implements = implements
        self.defaults = defaults
        self.generic = generic
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

    async def create(self, target, *args, **kwargs):
        """Create the target instance."""
        func = (
            functools.partial(self.func, target if self.generic else self.owner)
            if self.owner
            else self.func
        )
        if inspect.iscoroutinefunction(self.func):
            adapted = await func(*args, **kwargs)
        else:
            adapted = func(*args, **kwargs)
        return adapted


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
            return_type = hints["return"]
            self.adapter.implements = return_type
            self.adapters.add(return_type, self.adapter)
            # test for generic type
            if typing_inspect.is_typevar(return_type):
                # register generic adapter
                localns = {**self.adapter.locals, owner.__name__: owner}
                bound_generic_type = typing_inspect.get_bound(return_type)
                if bound_generic_type is None:
                    if typing_inspect.is_generic_type(owner):
                        bound_type = owner
                    else:
                        raise AdapterError(
                            "Generic adapter type is not bound to a type",
                            return_type,
                        )
                else:
                    bound_type = getattr(
                        bound_generic_type,
                        "_eval_type" if PY_36 else "_evaluate",
                    )(self.adapter.globals, localns)

                self.adapters.generic_index[bound_type] = return_type
                self.adapter.generic = True

        except NameError:
            pass

    def __get__(self, instance, owner):
        if owner is None:
            owner = type(instance)
        return functools.partial(self.adapter.func, owner)


cdef class Adapters:
    cdef dict _index
    cdef dict _generic_index
    def __init__(self):
        self._index = {}
        self._generic_index = {}

    @property
    def index(self):
        return self._index

    @property
    def generic_index(self):
        return self._generic_index

    cdef _add(self, target, adapter):
        if target in self._index:
            self._index[target].insert(0, adapter)
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
            spec = inspect.getfullargspec(func.__init__)
            spec.args.pop(0)
            implements = func
        else:
            spec = inspect.getfullargspec(func)
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

    def get_possible_adapters(self, target, default):
        # try to adapt
        if target in self.index:
            yield from self.index[target]
        yield from self._find_string_target_adapters(target)

        # find generic adapters
        for base in inspect.getmro(target):
            if base in self.generic_index:
                yield from self.index[self.generic_index[base]]

    async def resolve_adapter(self, Components cmps, object target, *, name=None, default=missing):
        cdef object component
        # find in components
        try:
            component = _get_name_or_default(cmps, target, name)
            return component
        except ComponentLookupError:
            pass

        cdef list resolve_errors = []
        cdef Adapter adptr
        cdef dict adapter_args
        possible_adapters = self.get_possible_adapters(target, default)
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
                component = await adptr.create(target, **adapter_args)
                # we do not use the name
                cmps._add(component)
                return component

        if default is not missing:
            return default

        try:
            # have we tried at least one adapter
            adptr
        except NameError:
            raise ResolveError("No possible adapter found", target, [])
        raise ResolveError("No adapter dependencies found", target, resolve_errors)


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
