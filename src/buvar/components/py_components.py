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

    def __iter__(self):
        return iter(self.upstream())

    def add(self, item, namespace=None, *, name=None):
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

    def upstream(self, target=missing, name=missing):
        spaces = {}

        target_is_class = isinstance(target, type)
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

    def find(self, namespace):
        merged = {}
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

    def get(self, namespace, *, name=None, default=missing):
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
