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

    def push(self, namespaces=None, *stack):
        """Push a whole stack on top of the actual components or just a new
        bare namespaces one.
        """
        if namespaces is None:
            namespaces = {}

        components = self.__class__(namespaces, *itertools.chain(stack, self.stack))
        return components

    def pop(self):
        return self.__class__(*self.stack[1:])

    cdef dict upstream(self, target=missing, name=missing):
        cdef dict space
        cdef dict merged
        cdef dict namespaces
        cdef dict spaces = {}
        cdef bint target_is_class = isinstance(target, type)

        for namespaces in self.stack[::-1]:
            for namespace, space in namespaces.items():
                if target is not missing:
                    if target_is_class and isinstance(namespace, type):
                        if not issubclass(namespace, target):
                            continue
                    elif target != namespace:
                        continue

                if namespace in spaces:
                    if name is missing:
                        spaces[namespace].update(space)
                    elif name in space:
                        spaces[namespace][name] = space[name]
                else:
                    if name is missing:
                        merged = dict(space)
                    elif name in space:
                        merged = {name: space[name]}
                    else:
                        # XXX name not in space
                        continue
                    spaces[namespace] = merged
        return spaces

    cdef dict _find(self, object namespace):
        cdef dict spaces
        cdef dict merged = {}

        spaces = self.upstream(target=namespace)
        # sort after mro
        if isinstance(namespace, type):
            for cls in (namespace,) + namespace.__mro__[::-1]:
                for key in spaces:
                    if issubclass(key, cls):
                        merged.update(spaces[key])
                        # stop if we found something
                        break
        else:
            merged.update(spaces[namespace])
        return merged

    def find(self, namespace):
        return self._find(namespace)

    cdef _get(self, object namespace, str name=None, default=missing):
        spaces = self.upstream(target=namespace, name=name)
        # sort after mro
        for key in spaces:
            space = spaces[key]
            if isinstance(key, type):
                for cls in (namespace,) + namespace.__mro__[::-1]:
                    if issubclass(key, cls) and name in space:
                        return space[name]
            elif name in space:
                return space[name]
        if default is missing:
            raise ComponentLookupError("Component not found", namespace, name, default)
        return default

    def get(self, namespace, *, name=None, default=missing):
        item = self._get(namespace, name=name, default=default)
        return item
