# cython: language_level=3
"""Self made components.

stacked::
    - each layer is the destination of additions, no inferior layer is affected
    - find collects all stacked namespaces, where superior names overwrite
      inferior ones
"""
import itertools

missing = object()


cdef class ComponentLookupError(Exception):
    pass


cdef class Components:
    def __init__(self, *stack):
        self.stack = list(stack) or [{}]  # always at least one map
        self.namespaces = self.stack[0]

    def __iter__(self):
        return iter(self.upstream())

    cdef _add(self, object item, namespace=None, str name=None):
        cdef dict space

        if isinstance(item, type):
            raise ValueError("A component should be an instance.")

        if namespace is None:
            namespace = type(item)

        if isinstance(namespace, type):
            mro = namespace.__mro__
        else:
            mro = [namespace]

        # we add the whole MRO to have a fast lookup later
        for namespace in mro:
            if namespace in self.namespaces:
                self.namespaces[namespace][name] = item
            else:
                space = {name: item}
                self.namespaces[namespace] = space
        return item

    def add(self, item, namespace=None, *, name=None):
        if isinstance(item, type):
            raise ValueError("A component should be an instance.")
        return self._add(item, namespace, name=name)

    cdef _push(self, namespaces, stack):
        if namespaces is None:
            namespaces = {}

        components = self.__class__(namespaces, *itertools.chain(stack, self.stack))
        return components

    def push(self, namespaces=None, *stack):
        """Push a whole stack on top of the actual components or just a new
        bare namespaces one.
        """
        return self._push(namespaces, stack)

    cpdef pop(self):
        return self.__class__(*self.stack[1:])

    cdef dict _find(self, namespace):
        cdef dict merged = {}
        for namespaces in self.stack[::-1]:
            try:
                space = namespaces[namespace]
                merged.update(space)
            except KeyError:
                pass
        return merged

    def find(self, namespace):
        return self._find(namespace)

    cdef _get(self, namespace, name=None, default=missing):
        for namespaces in self.stack:
            try:
                item = namespaces[namespace][name]
                return item
            except KeyError:
                pass

        if default is missing:
            raise ComponentLookupError("Component not found", namespace, name, default)
        return default

    def get(self, namespace, *, name=None, default=missing):
        item = self._get(namespace, name=name, default=default)
        return item
