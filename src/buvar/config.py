import os
import sys
import typing

import attr
import structlog
import tomlkit

CNF_KEY = "buvar_config"


logger = structlog.get_logger()


missing = object()


@attr.s(auto_attribs=True)
class ConfigValue:
    name: str = None
    help: str = None


def var(
    default=missing, converter=None, name=None, validator=None, help=None
):  # noqa: W0622
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
    if val in ("1", "true", "yes", "on"):
        return True

    return False


def _env_to_list(val):
    """Take a comma separated string and split it."""
    if isinstance(val, str):
        val = map(lambda x: x.trim(), val.split(","))
    return val


def bool_var(default=missing, name=None, help=None):  # noqa: W0622
    return var(default=default, name=name, converter=_env_to_bool, help=help)


def list_var(default=missing, name=None, help=None):  # noqa: W0622
    return var(default=default, name=name, converter=_env_to_list, help=help)


@attr.s(auto_attribs=True)
class BuvarConfig:
    log_level: str = var(help="The log level to set")
    include: typing.List[str] = list_var(help="A list of plugins to include")


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

    def load(self, scheme, name=...):
        if name is ...:
            values = self
        else:
            values = self[name]

        scheme = schematize(
            scheme,
            values,
            env_prefix="_".join(
                part
                for part in (self.env_prefix, name.upper() if name is not ... else None)
                if part
            ),
        )
        return scheme


def isattrs(obj):
    return hasattr(obj, "__attrs_attrs__")


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
    assert isattrs(attrs), f"{attrs} must be attrs decorated"
    for attrib in attrs.__attrs_attrs__:
        a_name = attrib.name
        env_name = "_".join(part for part in (env_prefix, a_name.upper()) if part)
        try:
            if isattrs(attrib.type):
                a_value = schematize(attrib.type, source[a_name], env_prefix=env_name)
            else:
                a_value = os.environ.get(env_name, source.get(a_name, missing))
                if a_value is missing:
                    if attrib.default is missing:
                        raise ValueError("Attribute is missing", a_name, env_name)
                    # we skip this value if source is lacking but we have a default
                    continue
                if attrib.converter is None:
                    if attrib.type is typing.List:
                        a_value = list(a_value)
                    else:
                        # cast type
                        a_value = attrib.type(a_value)
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
        if not isattrs(attrib)
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
        if isattrs(attrib.type):
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
        if isattrs(attrib.type):
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
