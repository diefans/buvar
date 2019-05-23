import pytest


def test_lookup_mro():
    from buvar import components

    class Foo:
        pass

    class Bar(Foo):
        pass

    class Baz(Bar):
        pass

    c = components.Components()

    foo = Foo()
    baz = Baz()
    c.add(foo)
    c.add(baz)

    assert c.get(Foo) == foo
    assert c.get(Bar) == baz
    assert c.get(Baz) == baz


def test_lookup_basic():
    from buvar import components
    c = components.Components()

    c.add('foo', 'bar')

    assert c.get('bar') == 'foo'


def test_no_instance():
    from buvar import components
    c = components.Components()

    class Foo:
        pass

    with pytest.raises(ValueError):
        c.add(Foo)
