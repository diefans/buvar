import pytest


# @pytest.mark.skipif(
#     sys.version_info < (3, 7),
#     reason="similar to https://github.com/python/typing/issues/506",
# )
@pytest.mark.asyncio
async def test_config_source_schematize(mocker):
    from buvar import config
    import typing
    import attr

    @attr.s(auto_attribs=True)
    class FooConfig:
        bar: str = "default"
        foobar: float = 9.87
        baz: bool = False

    @attr.s(auto_attribs=True)
    class BarConfig:
        bim: float
        foo: FooConfig = FooConfig()

    @attr.s(auto_attribs=True, kw_only=True)
    class BimConfig:
        bar: BarConfig
        bam: bool
        bum: int = 123
        lst: typing.List

    sources = [
        {"bar": {"bim": "123.4", "foo": {"bar": "1.23", "baz": "true"}}},
        {"foo": {"bar": "value", "foobar": 123.5, "baz": True}},
        {
            "bar": {"bim": "123.4"},
            "bim": {"bar": {"bim": 1.23}, "bam": "on", "lst": [1, 2, 3]},
        },
    ]

    mocker.patch(
        "os.environ",
        {
            "PREFIX_BAR_BIM": "0",
            "PREFIX_BAR_FOO_FOOBAR": "7.77",
            "PREFIX_BAR_FOO_BAZ": "false",
        },
    )

    cfg = config.ConfigSource(*sources, env_prefix="PREFIX")
    # foo_config = await adapters.nject(FooConfig, source=cfg)

    bim = cfg.load(BimConfig, "bim")
    bar = cfg.load(BarConfig, "bar")
    foo = cfg.load(FooConfig, "foo")
    # (FooConfig(bar="value", foobar=123.5, baz=True),)

    assert (bar, foo, bim) == (
        BarConfig(bim=0.0, foo=FooConfig(bar="1.23", foobar=7.77, baz=False)),
        FooConfig(bar="value", foobar=123.5, baz=True),
        BimConfig(bar=BarConfig(bim=1.23), bam=True, lst=[1, 2, 3]),
    )


@pytest.mark.asyncio
@pytest.mark.buvar_plugins("buvar.config")
async def test_config_generic_adapter(mocker):
    import attr
    import typing
    from buvar import config, di

    mocker.patch.dict(config.Config.__buvar_config_sections__, clear=True)

    @attr.s(auto_attribs=True)
    class FooConfig(config.Config, section="foo"):
        bar: str = "default"
        foobar: float = 9.87
        baz: bool = False

    @attr.s(auto_attribs=True)
    class BarConfig(config.Config, section="bar"):
        bim: float
        foo: FooConfig = FooConfig()

    @attr.s(auto_attribs=True, kw_only=True)
    class BimConfig(config.Config, section="bim"):
        bar: BarConfig
        bam: bool
        bum: int = 123
        lst: typing.List

    sources = [
        {"bar": {"bim": "123.4", "foo": {"bar": "1.23", "baz": "true"}}},
        {"foo": {"bar": "value", "foobar": 123.5, "baz": True}},
        {
            "bar": {"bim": "123.4"},
            "bim": {"bar": {"bim": 1.23}, "bam": "on", "lst": [1, 2, 3]},
        },
    ]

    mocker.patch(
        "os.environ",
        {
            "PREFIX_BAR_BIM": "0",
            "PREFIX_BAR_FOO_FOOBAR": "7.77",
            "PREFIX_BAR_FOO_BAZ": "false",
        },
    )

    cfg = config.ConfigSource(*sources, env_prefix="PREFIX")
    foo_config = await di.nject(FooConfig, source=cfg)
    assert foo_config == FooConfig(bar="value", foobar=123.5, baz=True)


def test_load_general_config():
    import attr
    import typing
    from buvar import config

    sources = [{"foo": "bar", "group": {"some": "value"}}]
    cfg = config.ConfigSource(*sources, env_prefix="PREFIX")

    @attr.s(auto_attribs=True)
    class GeneralVars:
        foo: str
        baz: typing.Optional[float] = None

    general = cfg.load(GeneralVars)
    assert general == GeneralVars("bar", None)


def test_config_missing():
    import attr
    from cattrs.errors import ClassValidationError
    from buvar import config

    source: dict = {"foo": {}}

    @attr.s(auto_attribs=True)
    class FooConfig:
        bar: str

    cfg = config.ConfigSource(source)
    with pytest.raises(ClassValidationError):
        cfg.load(FooConfig, "foo")


@pytest.mark.xfail
def test_generate_toml_help():
    import typing
    import attr
    from buvar import config

    @attr.s(auto_attribs=True)
    class FooConfig:
        """FooConfig.

        bim bam
        """

        string_val: str
        float_val: float = 9.87
        bool_val: bool
        int_val: int
        list_val: typing.List

    @attr.s(auto_attribs=True)
    class BarConfig:
        """BarConfig.

        bla bla
        bli bli
        """

        bim: float
        foo: FooConfig

    env_vars = {}
    config_fields = list(config.traverse_attrs(BarConfig, target=env_vars))

    assert {path for path, _, _ in config_fields} == {
        ("foo",),
        ("bim",),
        ("foo", "string_val"),
        ("foo", "float_val"),
        ("foo", "bool_val"),
        ("foo", "int_val"),
        ("foo", "list_val"),
    }

    help = config.generate_toml_help(BarConfig)
    assert (
        help.as_string()
        == """# BarConfig.
#
# bla bla
# bli bli

# bim =


[foo]
# FooConfig.
#
# bim bam

# string
# string_val =

# float
float_val = 9.87

# bool
# bool_val =

# int
# int_val =

# list
list_val = []

"""
    )  # noqa: W291


def test_nested_attrs_typing():
    import typing
    import attr
    from buvar import config

    @attr.s(auto_attribs=True)
    class Baz:
        baz: str = "foobar"

    @attr.s(auto_attribs=True)
    class Bar:
        baz: Baz

    @attr.s(auto_attribs=True)
    class Foo:
        bars: typing.List[Bar] = []

    source = config.ConfigSource(
        {"foo": {"bars": [{"baz": {"baz": "something else"}}]}}, env_prefix="TEST"
    )

    foo = source.load(Foo, "foo")
    assert foo == Foo(bars=[Bar(baz=Baz(baz="something else"))])


def test_env_config(mocker):
    from buvar import config
    import attr

    @attr.s(auto_attribs=True)
    class Baz:
        float: float

    @attr.s(auto_attribs=True)
    class Foo:
        str: str
        int: int
        baz: "Baz"

    @attr.s(auto_attribs=True)
    class Bar:
        foo: "Foo"

    mocker.patch("os.environ", {"PREFIX_FOO_STR": "abc", "PREFIX_FOO_INT": "777"})
    env_config = config.create_env_config(Bar, "PREFIX")

    assert env_config == {"foo": {"baz": {}, "str": "abc", "int": "777"}}


@pytest.mark.asyncio
@pytest.mark.buvar_plugins("buvar.config")
async def test_config_subclass_abc(mocker):
    import abc
    import attr
    from buvar import config, di

    mocker.patch.dict(config.Config.__buvar_config_sections__, clear=True)

    class GeneralConfig(config.Config, section=None): ...

    class FooBase(metaclass=abc.ABCMeta):
        @abc.abstractmethod
        def foo(self): ...

    @attr.s(auto_attribs=True)
    class FooConfig(config.Config, FooBase, section="foo"):
        bar: str

        def foo(self): ...

    assert config.skip_section not in config.Config.__buvar_config_sections__
    assert FooBase not in config.Config.__buvar_config_sections__.values()
    assert config.Config.__buvar_config_sections__["foo"] is FooConfig
    cfg = config.ConfigSource({"foo": {"bar": "abc"}}, env_prefix="PREFIX")
    foo_config = await di.nject(FooConfig, source=cfg)

    assert foo_config == FooConfig(bar="abc")
