import functools
import os
import sys
import typing

import attr
import cattr
import structlog
import tomlkit
import typing_inspect

from . import di, util

CNF_KEY = "buvar_config"


logger = structlog.get_logger()


# since we only need a single instance, we just hide the class magically
@functools.partial(lambda x: x())
class missing:
    def __repr__(self):
        return self.__class__.__name__


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


class ConfigError(Exception):
    ...


# to get typing_inspect.is_generic_type()
ConfigType = typing.TypeVar("ConfigType", bound="Config")

skip_section = type.__new__(
    type, "skip_section", (object,), {"__repr__": lambda self: self.__class__.__name__}
)()


class Config:
    __buvar_config_section__: typing.Optional[str] = skip_section
    __buvar_config_sections__: typing.Dict[str, type] = {}

    def __init_subclass__(cls, section: str = skip_section, **kwargs):
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


class RelaxedConverter(cattr.Converter):
    """This py:obj:`RelaxedConverter` is ignoring undefined and defaulting to
    None on optional attributes."""

    def structure_attrs_fromdict(
        self, obj: typing.Mapping, cl: typing.Type
    ) -> typing.Any:
        """Instantiate an attrs class from a mapping (dict)."""
        conv_obj = {}
        dispatch = self._structure_func.dispatch
        for a in attr.fields(cl):
            # We detect the type by metadata.
            type_ = a.type
            if type_ is None:
                # No type.
                continue
            name = a.name
            try:
                val = obj[name]
            except KeyError:
                if typing_inspect.is_optional_type(type_):
                    if a.default in (missing, attr.NOTHING):
                        val = None
                    else:
                        val = a.default
                elif a.default in (missing, attr.NOTHING):
                    raise ValueError("Attribute is missing", a.name)
                else:
                    continue

            if a.converter is None:
                val = dispatch(type_)(val, type_)

            conv_obj[name] = val

        return cl(**conv_obj)


relaxed_converter = RelaxedConverter()


def generate_env_help(cls, env_prefix=""):
    """Generate a list of all environment options."""

    help = "\n".join(  # noqa: W0622
        "_".join((env_prefix,) + path if env_prefix else path).upper()
        for path, type, _ in traverse_attrs(cls)
        if not attr.has(type)
    )
    return help


def generate_toml_help(config_cls, *, parent=None):
    if parent is None:
        parent = tomlkit.table()
        doclines = trim(config_cls.__doc__).split("\n")
        for line in doclines:
            parent.add(tomlkit.comment(line))
        parent.add(tomlkit.nl())

    for attrib in attr.fields(config_cls):
        meta = attrib.metadata.get(CNF_KEY)
        if attr.has(attrib.type):
            # yield (attrib.name,), attrib
            sub_doc = generate_toml_help(attrib.type)
            parent.add(attrib.name, sub_doc)
        else:
            if meta:
                parent.add(tomlkit.comment(meta.help))

            if attrib.default in (missing, attr.NOTHING):
                parent.add(tomlkit.comment(f"{attrib.name} ="))
            else:
                default = (
                    attrib.default() if callable(attrib.default) else attrib.default
                )
                parent.add(attrib.name, default)

            parent.add(tomlkit.nl())

    return parent


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


async def prepare():
    di.register(Config.adapt)
