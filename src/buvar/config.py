import os
import sys
import typing

import attr
import cattr
import structlog
import tomlkit
import typing_inspect

from . import di

CNF_KEY = "buvar_config"


logger = structlog.get_logger()


missing = object()


@attr.s(auto_attribs=True)
class ConfigValue:
    name: typing.Optional[str] = None
    help: typing.Optional[str] = None


def var(
    default=missing,
    converter=None,
    factory=missing,
    name=None,
    validator=None,
    help=None,  # noqa: W0622,
):
    return attr.ib(
        metadata={CNF_KEY: ConfigValue(name, help)},
        converter=converter,
        validator=validator,
        **({"default": default} if factory is missing else {"factory": factory}),
    )


def _env_to_bool(val):
    """
    Convert *val* to a bool if it's not a bool in the first place.
    """
    if isinstance(val, bool):
        return val
    val = val.strip().lower()
    if val in ("1", "true", "yes", "on"):
        return True

    return False


def _env_to_list(val):
    """Take a comma separated string and split it."""
    if isinstance(val, str):
        val = map(lambda x: x.strip(), val.split(","))
    return val


def bool_var(default=missing, name=None, help=None):  # noqa: W0622
    return var(default=default, name=name, converter=_env_to_bool, help=help)


def list_var(default=missing, name=None, help=None):  # noqa: W0622
    return var(default=default, name=name, converter=_env_to_list, help=help)


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

    def __init__(self, *sources, env_prefix=None):
        super().__init__()
        for source in sources:
            merge_dict(self, source)
        # config = schematize(__source, cls, env_prefix=env_prefix)
        self.env_prefix = env_prefix  # noqa: W0212

    def merge(self, source):
        merge_dict(self, source)

    def load(self, scheme, name=None):
        if name is None:
            values = self
        else:
            values = self.get(name, {})

        scheme = schematize(
            scheme,
            values,
            env_prefix="_".join(
                part
                for part in (
                    self.env_prefix,
                    name.upper() if name is not None else None,
                )
                if part
            ),
        )
        return scheme


class ConfigError(Exception):
    ...


# to get typing_inspect.is_generic_type()
ConfigType = typing.TypeVar("ConfigType", bound="Config")


class Config:
    __buvar_config_sections__ = {}

    def __init_subclass__(cls, section=None, **kwargs):
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


def schematize(attrs, source, env_prefix=""):
    """Create a scheme from the source dict and apply environment vars."""
    attrs_kwargs = {}
    assert attr.has(attrs), f"{attrs} must be attrs decorated"
    for attrib in attrs.__attrs_attrs__:
        hints = typing.get_type_hints(attrs)
        a_type = attrib.type
        a_name = attrib.name
        a_hint = hints[a_name]
        env_name = "_".join(part for part in (env_prefix, a_name.upper()) if part)
        try:
            if attr.has(a_type):
                a_value = schematize(a_type, source[a_name], env_prefix=env_name)
            else:
                a_value = os.environ.get(env_name, source.get(a_name, missing))

                if a_value is missing:
                    if typing_inspect.is_optional_type(a_hint):
                        a_value = None
                    else:
                        if attrib.default is missing:
                            raise ValueError("Attribute is missing", a_name, env_name)
                        # we skip this value if source is lacking but we have a default
                        continue
                elif attrib.converter is None:
                    a_value = cattr.structure(a_value, a_type)

            attrs_kwargs[a_name] = a_value
        except KeyError:
            logger.warn("Key not in source", key=a_name, source=source)

    scheme = attrs(**attrs_kwargs)
    return scheme


def generate_env_help(attrs, env_prefix=""):
    """Generate a list of all environment options."""

    help = "\n".join(  # noqa: W0622
        "_".join((env_prefix,) + path if env_prefix else path).upper()
        for path, attrib in traverse_attrs(attrs)
        if not attr.has(attrib)
    )
    return help


def generate_toml_help(attrs, env_prefix="", parent=None):
    if parent is None:
        parent = tomlkit.table()
        doclines = trim(attrs.__doc__).split("\n")
        for line in doclines:
            parent.add(tomlkit.comment(line))
        parent.add(tomlkit.nl())

    for attrib in attrs.__attrs_attrs__:
        meta = attrib.metadata.get(CNF_KEY)
        if attr.has(attrib.type):
            # yield (attrib.name,), attrib
            sub_doc = generate_toml_help(attrib.type)
            parent.add(attrib.name, sub_doc)
        else:
            if meta:
                parent.add(tomlkit.comment(meta.help))

            if attrib.default not in (missing, attr.NOTHING):
                default = (
                    attrib.default() if callable(attrib.default) else attrib.default
                )

                parent.add(attrib.name, default)
            else:
                parent.add(tomlkit.comment(f"{attrib.name} ="))

            parent.add(tomlkit.nl())

    return parent


def traverse_attrs(attrs, with_nodes=False):
    for attrib in attrs.__attrs_attrs__:
        if attr.has(attrib.type):
            if with_nodes:
                yield (attrib.name,), attrib
            for path, sub_attrib in traverse_attrs(attrib.type):
                yield (attrib.name,) + path, sub_attrib
        else:
            yield (attrib.name,), attrib


def trim(docstring):
    # https://www.python.org/dev/peps/pep-0257/
    if not docstring:
        return ""
    # Convert tabs to spaces (following the normal Python rules)
    # and split into a list of lines:
    lines = docstring.expandtabs().splitlines()
    # Determine minimum indentation (first line doesn't count):
    indent = sys.maxsize
    for line in lines[1:]:
        stripped = line.lstrip()
        if stripped:
            indent = min(indent, len(line) - len(stripped))
    # Remove indentation (first line is special):
    trimmed = [lines[0].strip()]
    if indent < sys.maxsize:
        for line in lines[1:]:
            trimmed.append(line[indent:].rstrip())
    # Strip off trailing and leading blank lines:
    while trimmed and not trimmed[-1]:
        trimmed.pop()
    while trimmed and not trimmed[0]:
        trimmed.pop(0)
    # Return a single string:
    return "\n".join(trimmed)


async def plugin():
    di.register(Config.adapt)
