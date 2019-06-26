"""A simple component architecture.

must have:
- add components by their type and a name
- add components by someother discriminator
- lookup components by their type/discriminator and name
- find components just by their type


nice to have:
- adaption resp. dependency injection of components
"""
import collections
import inspect


missing = object()


class ComponentLookupError(Exception):
    pass


class Components:

    """A component registry holds certain items identified by a
    discriminator."""

    __slots__ = ("index",)

    def __init__(self, index=None):
        self.index = None
        self.push(index)

    def clone(self):
        return self.__class__(self.index)

    def push(self, index=None):
        if index is None:
            index = {}
        self.index = (
            collections.ChainMap(index)
            if self.index is None
            else self.index.new_child(index)
        )
        return index

    def pop(self):
        index = self.index.maps[0]
        self.index = self.index.parents
        return index

    def __repr__(self):
        return self.index.__repr__()

    def add(self, item, namespace=None, *, name=None):
        """Register `item` and optionally name it."""
        if inspect.isclass(item):
            raise ValueError("A component should be an instance.")
        if namespace is None:
            namespace = type(item)

        if namespace in self.index:
            self.index[namespace][name] = item
        else:
            self.index[namespace] = {name: item}

    def get(self, namespace, *, name=None, default=missing):
        try:
            item = self.find(namespace)[name]
        except KeyError:
            if default is missing:
                raise ComponentLookupError(
                    "Component not found", namespace, name, default
                )
            return default
        return item

    def find(self, namespace):
        items = self._lookup(namespace)
        return items

    def _lookup(self, namespace):
        """Try to match the discriminator.

        If more than one component matches the discriminator, we return the
        closest one.
        """
        if inspect.isclass(namespace):
            items = None
            for key in self.index.keys():
                if inspect.isclass(key) and issubclass(key, namespace):
                    if items is None or issubclass(items, key):
                        items = key

        else:
            items = namespace

        return self.index[items]
