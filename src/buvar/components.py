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
import structlog


sl = structlog.get_logger()
missing = object()


class ComponentLookupError(Exception):
    pass


class Components(collections.ChainMap):

    """A component registry holds certain items identified by a
    namespace discriminator."""

    def add(self, item, namespace=None, *, name=None):
        """Register `item` and optionally name it."""
        if inspect.isclass(item):
            raise ValueError("A component should be an instance.")
        if namespace is None:
            namespace = type(item)

        if namespace in self:
            self[namespace][name] = item
        else:
            self[namespace] = {name: item}
        return item

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
        """Try to match the discriminator.

        If more than one component matches the discriminator, we return the
        closest one.
        """
        if inspect.isclass(namespace):
            items = None
            for key in self.keys():
                if inspect.isclass(key) and issubclass(key, namespace):
                    if items is None or issubclass(items, key):
                        items = key

        else:
            items = namespace

        return self[items]
