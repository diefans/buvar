import os

import attr
import structlog

CNF_KEY = 'buvar_config'


logger = structlog.get_logger()


missing = object()


@attr.s(auto_attribs=True)
class Config:

    """Config dict, with loadable sections.

    >>> @attr.s(auto_attribs=True)
    ... class FooConfig:
    ...     bar: float
    >>>
    >>>
    >>> source = {'foo': {'bar': 1.23}}
    >>> config = Config.from_sources(source)
    >>> config.foo = FooConfig
    >>> config.foo
    FooConfig(bar=1.23)
    """

    __slots__ = ('__source', '__dict__', '__env_prefix')

    @classmethod
    def from_sources(cls, *sources, env_prefix=None):
        __source = {}
        for source in sources:
            merge_dict(__source, source)

        config = schematize(__source, cls, env_prefix=env_prefix)
        config.__env_prefix = env_prefix        # noqa: W0212
        config.__source = __source              # noqa: W0212
        return config

    def __setattr__(self, name, value):
        """Load a source section by applying the `scheme` upon it."""
        if hasattr(value, '__attrs_attrs__'):
            value = self.__process_scheme(name, value)
        super().__setattr__(name, value)
    __setitem__ = __setattr__

    def __process_scheme(self, name, scheme):
        values = self.__source[name]
        scheme = schematize(
            values, scheme,
            env_prefix='_'.join(
                part for part in (self.__env_prefix, name.upper()) if part
            )
        )
        return scheme


@attr.s(auto_attribs=True)
class ConfigValue:
    name: str = None
    help: str = None


def var(default=missing, converter=None, name=None, validator=None, help=None):    # noqa: W0622
    return attr.ib(
        default=default,
        metadata={CNF_KEY: ConfigValue(name, help)},
        converter=converter,
        validator=validator,
    )


def _env_to_bool(val):
    """
    Convert *val* to a bool if it's not a bool in the first place.
    """
    if isinstance(val, bool):
        return val
    val = val.strip().lower()
    if val in ('1', 'true', 'yes', 'on'):
        return True

    return False


def bool_var(default=missing, name=None, help=None):   # noqa: W0622
    return var(default=default, name=name, converter=_env_to_bool, help=help)


def isattrs(obj):
    return hasattr(obj, '__attrs_attrs__')


def merge_dict(dest, source):
    """Merge `source` into `dest`.

    `dest` is altered in place.
    """
    for key, value in source.items():
        if isinstance(value, dict):
            # get node or create one
            node = dest.setdefault(key, {})
            merge_dict(node, value)
        else:
            dest[key] = value
    return dest


def schematize(source, attrs, env_prefix=''):
    """Create a scheme from the source dict and apply environment vars."""
    attrs_kwargs = {}
    assert isattrs(attrs), f'{attrs} must be attrs decorated'
    for attrib in attrs.__attrs_attrs__:
        a_name = attrib.name
        env_name = '_'.join(
            part for part in (env_prefix, a_name.upper()) if part
        )
        try:
            if isattrs(attrib.type):
                a_value = schematize(source[a_name],
                                     attrib.type,
                                     env_prefix=env_name)
            else:
                a_value = os.environ.get(env_name, source.get(a_name, ...))
                # we skip this value if source is lacking
                if a_value is ...:
                    continue
                if attrib.converter is None:
                    # cast type
                    a_value = attrib.type(a_value)
            attrs_kwargs[a_name] = a_value
        except KeyError:
            logger.warn('Key not in source', key=a_name, source=source)

    scheme = attrs(**attrs_kwargs)
    return scheme
