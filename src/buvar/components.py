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


class Components:

    """A component registry holds certain items identified by a
    discriminator."""

    __slots__ = ('_index',)

    def __init__(self):
        self._index = collections.defaultdict(dict)

    def __repr__(self):
        return self._index.__repr__()

    def add(self, item, namespace=None, *, name=None):
        """Register `item` and optionally name it."""
        if inspect.isclass(item):
            raise ValueError('A component should be an instance.')
        if namespace is None:
            namespace = type(item)

        self._index[namespace][name] = item

    def get(self, namespace, *, name=None, default=None):
        item = self.find(namespace).get(name, default)
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
            for key in self._index.keys():
                if inspect.isclass(key) \
                        and issubclass(key, namespace):
                    if items is None \
                            or issubclass(items, key):
                        items = key

        else:
            items = namespace

        return self._index[items]
