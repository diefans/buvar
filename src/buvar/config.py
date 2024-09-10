import functools
import os
import sys
import typing

import attr
import cattr
import structlog

from . import di, util

logger = structlog.get_logger()


@attr.s(auto_attribs=True)
class ConfigValue:
    name: typing.Optional[str] = None
    help: typing.Optional[str] = None


class ConfigSource(dict):
    """Config dict, with loadable sections.

    >>> @attr.s(auto_attribs=True)
    ... class FooConfig:
    ...     bar: float
    >>>
    >>>
    >>> source = {'foo': {'bar': 1.23}}
    >>> config = ConfigSource(source)
    >>> foo = config.load(FooConfig, "foo")
    >>> foo
    FooConfig(bar=1.23)
    """

    __slots__ = ("env_prefix",)

    def __init__(self, *sources, env_prefix: typing.Optional[str] = None):
        super().__init__()
        util.merge_dict(*sources, dest=self)
        # config = schematize(__source, cls, env_prefix=env_prefix)

        self.env_prefix: typing.Tuple[str, ...] = (env_prefix,) if env_prefix else ()

    def merge(self, *sources):
        util.merge_dict(*sources, dest=self)

    def load(self, config_cls, name=None):
        if name is None:
            values = self
        else:
            values = self.get(name, {})

        env_config = create_env_config(
            config_cls, *(self.env_prefix + ((name,) if name else ()))
        )
        values = util.merge_dict(values, env_config)
        # merge environment

        config = relaxed_converter.structure(values, config_cls)
        return config


class ConfigError(Exception): ...


# to get typing_inspect.is_generic_type()
ConfigType = typing.TypeVar("ConfigType", bound="Config")

skip_section = type.__new__(
    type, "skip_section", (object,), {"__repr__": lambda self: self.__class__.__name__}
)()


class Config:
    __buvar_config_section__: typing.Optional[str] = skip_section
    __buvar_config_sections__: typing.Dict[str, type] = {}

    def __init_subclass__(cls, *, section: str = skip_section, **_):
        if section is skip_section:
            return
        if section in cls.__buvar_config_sections__:
            raise ConfigError(
                f"Config section `{section}` already defined!",
                cls.__buvar_config_sections__,
                cls,
            )
        cls.__buvar_config_section__ = section
        cls.__buvar_config_sections__[section] = cls

    @classmethod
    async def adapt(cls: typing.Type[ConfigType], source: ConfigSource) -> ConfigType:
        config = source.load(cls, cls.__buvar_config_section__)
        return config


def traverse_attrs(cls, *, target=None, get_type_hints=typing.get_type_hints):
    """Traverse a nested attrs structure, create a dictionary for each nested
    attrs class and yield all fields resp. path, type and target dictionary."""
    stack = [
        (
            target if target is not None else {},
            (),
            list(attr.fields(cls)),
            get_type_hints(cls),
        )
    ]
    while stack:
        target, path, fields, hints = stack.pop()
        while fields:
            field = fields.pop()
            field_path = path + (field.name,)
            field_type = hints[field.name]
            if attr.has(field_type):
                target[field.name] = field_target = {}
                # XXX should we yield also attrs classes?
                yield field_path, field_type, target

                stack.append((target, path, fields, hints))
                target, path, fields, hints = (
                    field_target,
                    field_path,
                    list(attr.fields(field_type)),
                    get_type_hints(field_type),
                )
            else:
                yield field_path, field_type, target


def create_env_config(cls, *env_prefix):
    frame = sys._getframe(1)
    get_type_hints = functools.partial(
        typing.get_type_hints, globalns=frame.f_globals, localns=frame.f_locals
    )

    env_config = {}
    for path, _, target in traverse_attrs(
        cls, target=env_config, get_type_hints=get_type_hints
    ):
        env_name = "_".join(map(lambda x: x.upper(), env_prefix + path))
        if env_name in os.environ:
            logger.debug("Overriding config by env", var=env_name)
            target[path[-1]] = os.environ[env_name]
    return env_config


# FIXME: deprecate relaxed_converter
converter = relaxed_converter = cattr.Converter()


def _env_to_bool(val, type):
    """
    Convert *val* to a bool if it's not a bool in the first place.
    """
    if isinstance(val, type):
        return val
    elif isinstance(val, str):
        val = val.strip().lower()
        if val in ("1", "true", "yes", "on"):
            return True

    return False


relaxed_converter.register_structure_hook(bool, _env_to_bool)


def generate_env_help(cls, env_prefix=""):
    """Generate a list of all environment options."""

    help = "\n".join(  # noqa: W0622
        "_".join((env_prefix,) + path if env_prefix else path).upper()
        for path, type, _ in traverse_attrs(cls)
        if not attr.has(type)
    )
    return help


async def prepare():
    di.register(Config.adapt)
