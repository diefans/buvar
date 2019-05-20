import pytest


def test_config_source_schematize(mocker):
    import buvar
    import attr

    @attr.s(auto_attribs=True)
    class FooConfig:
        bar: str = 'default'
        foobar: float = 9.87
        baz: bool = buvar.bool_var(default=False)

    @attr.s(auto_attribs=True)
    class BarConfig:
        bim: float
        foo: FooConfig = FooConfig()

    @attr.s(auto_attribs=True, kw_only=True)
    class BimConfig:
        bar: BarConfig
        bam: bool = buvar.bool_var()
        bum: int = 123

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
                'bam': 'on'
            },
        }
    ]

    mocker.patch('os.environ', {
        'PREFIX_BAR_BIM': '0',
        'PREFIX_BAR_FOO_FOOBAR': '7.77',
        'PREFIX_BAR_FOO_BAZ': 'false'
    })

    cfg = buvar.Config.from_sources(*sources, env_prefix='PREFIX')
    cfg.bar = BarConfig
    cfg.foo = FooConfig
    cfg.bim = BimConfig

    assert cfg.__dict__ == {
        'bar': BarConfig(bim=0.0, foo=FooConfig(bar='1.23', foobar=7.77, baz=False)),
        'foo': FooConfig(bar='value', foobar=123.5, baz=True),
        'bim': BimConfig(bar=BarConfig(bim=1.23), bam=True),
    }

    assert cfg.foo.baz


def test_config_missing():
    import attr
    import buvar

    source = {
        'foo': {
        }
    }

    @attr.s(auto_attribs=True)
    class FooConfig:
        bar: str = buvar.var()

    cfg = buvar.Config.from_sources(source)
    with pytest.raises(ValueError):
        cfg.foo = FooConfig
