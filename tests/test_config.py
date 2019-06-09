import pytest


def test_config_source_schematize(mocker):
    from buvar import config
    import typing
    import attr

    @attr.s(auto_attribs=True)
    class FooConfig:
        bar: str = 'default'
        foobar: float = 9.87
        baz: bool = config.bool_var(default=False)

    @attr.s(auto_attribs=True)
    class BarConfig:
        bim: float
        foo: FooConfig = FooConfig()

    @attr.s(auto_attribs=True, kw_only=True)
    class BimConfig:
        bar: BarConfig
        bam: bool = config.bool_var()
        bum: int = config.var(123)
        lst: typing.List = config.var(list)

    sources = [
        {
            'bar': {
                'bim': '123.4',
                'foo': {
                    'bar': '1.23',
                    'baz': 'true',
                },
            },
        }, {
            'foo': {
                'bar': 'value',
                'foobar': 123.5,
                'baz': True,
            }
        }, {
            'bar': {
                'bim': '123.4',
            },
            'bim': {
                'bar': {
                    'bim': 1.23
                },
                'bam': 'on',
                'lst': [1, 2, 3],
            },
        }
    ]

    mocker.patch('os.environ', {
        'PREFIX_BAR_BIM': '0',
        'PREFIX_BAR_FOO_FOOBAR': '7.77',
        'PREFIX_BAR_FOO_BAZ': 'false'
    })

    cfg = config.Config.from_sources(*sources, env_prefix='PREFIX')
    cfg.bar = BarConfig
    cfg.foo = FooConfig
    cfg.bim = BimConfig

    assert cfg.__dict__ == {
        'bar': BarConfig(bim=0.0, foo=FooConfig(bar='1.23', foobar=7.77, baz=False)),
        'foo': FooConfig(bar='value', foobar=123.5, baz=True),
        'bim': BimConfig(bar=BarConfig(bim=1.23), bam=True, lst=[1, 2, 3]),
    }

    assert cfg.foo.baz


def test_config_missing():
    import attr
    from buvar import config

    source = {
        'foo': {
        }
    }

    @attr.s(auto_attribs=True)
    class FooConfig:
        bar: str = config.var()

    cfg = config.Config.from_sources(source)
    with pytest.raises(ValueError):
        cfg.foo = FooConfig


def test_subclass():
    import attr
    from buvar import config

    source = {
        'bar': 'foobar',
    }

    @attr.s(auto_attribs=True)
    class FooConfig(config.Config):
        bar: str = config.var()

    cfg = FooConfig.from_sources(source)
    assert cfg == FooConfig(bar='foobar')


def test_generate_toml_help():
    import typing
    import attr
    from buvar import config

    @attr.s(auto_attribs=True)
    class FooConfig:
        """FooConfig.

        bim bam
        """
        string_val: str = config.var(help='string')
        float_val: float = config.var(9.87, help='float')
        bool_val: bool = config.bool_var(help='bool')
        int_val: int = config.var(help='int')
        list_val: typing.List = config.var(list, help='list')

    @attr.s(auto_attribs=True)
    class BarConfig:
        """BarConfig.

        bla bla
        bli bli
        """
        bim: float
        foo: FooConfig = config.var(help='foo')

    env_vars = list(config.traverse_attrs(BarConfig))

    assert [path for path, _ in env_vars] == [
        ('bim',),
        ('foo', 'string_val'),
        ('foo', 'float_val'),
        ('foo', 'bool_val'),
        ('foo', 'int_val'),
        ('foo', 'list_val'),
    ]

    help = config.generate_toml_help(BarConfig, env_prefix='PREFIX')
    assert help.as_string() == """# BarConfig.
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

""" # noqa: W291
