"""A simple component architecture.

must have:
- add components by their type and a name
- add components by someother discriminator
- lookup components by their type/discriminator and name
- find components just by their type


nice to have:
- adaption resp. dependency injection of components
"""
import itertools


missing = object()


class ComponentLookupError(Exception):
    pass


class Components:
    """A component registry holds certain items identified by a
    namespace discriminator."""

    def __init__(self, *stack):
        self.stack = list(stack) or [{}]  # always at least one map
        self.namespaces = self.stack[0]

    def add(self, item, namespace=None, *, name=None):
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

    def find(self, namespace):
        merged = {}
        for namespaces in self.stack[::-1]:
            try:
                space = namespaces[namespace]
                merged.update(space)
            except KeyError:
                pass
        return merged

    def get(self, namespace, *, name=None, default=missing):
        for namespaces in self.stack:
            try:
                item = namespaces[namespace][name]
                return item
            except KeyError:
                pass

        if default is missing:
            raise ComponentLookupError("Component not found", namespace, name, default)
        return default
