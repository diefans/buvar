import pytest


@pytest.mark.benchmark(group="get")
def test_components_get(benchmark):
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

    def test():
        assert c.get(Bar) == baz
        assert c.get(Foo) == baz
        assert c.get(Baz) == baz

    benchmark(test)


def test_components_get_basic():
    from buvar import components

    c = components.Components()

    c.add("foo", "bar")

    assert c.get("bar") == "foo"


def test_components_get_bytes_name():
    from buvar import components

    c = components.Components()

    c.add("foo", b"bar")

    assert c.get(b"bar") == "foo"


def test_components_no_instance():
    from buvar import components

    c = components.Components()

    class Foo:
        pass

    with pytest.raises(ValueError):
        c.add(Foo)


def test_components_deep_find():
    from buvar import components

    c = components.Components()
    c.add("foo")
    cc = c.push()
    cc.add("bar", name="bar")

    assert c.find(str) == {None: "foo"}
    assert cc.find(str) == {None: "foo", "bar": "bar"}


@pytest.fixture
def components():
    from buvar import components

    yield components


@pytest.mark.benchmark(group="find")
def test_components_find(benchmark, components):
    class Foo:
        pass

    class Bar(Foo):
        pass

    c1 = components.Components()
    c2 = c1.push()
    c3 = c2.push()
    c4 = c3.push()

    foo = c1.add(Foo())
    bar = c2.add(Bar(), name="bar")
    foobar = c3.add(Foo(), name="bar")
    barbar = c4.add(Bar(), name="bar")

    def find():
        assert c3.find(Foo) == {None: foo, "bar": foobar}
        assert c3.find(Bar) == {"bar": bar}
        assert c4.find(Bar) == {"bar": barbar}

        assert c3.get(Bar, name="bar") == bar
        assert c4.get(Bar, name="bar") == barbar

    benchmark(find)


def test_componentsn_find_str(components):
    c = components.Components()
    c.add("foo", "foo")

    space = c.find("foo")
    assert space == {None: "foo"}


@pytest.mark.benchmark(group="push pop")
def test_components_push_pop(benchmark, components):
    c = components.Components()
    c.add("foo")

    def pushpop():
        cc = c.push()
        cc.add("bar", name="bar")
        assert c.find(str) == cc.pop().find(str)

    benchmark(pushpop)

    assert c.find(str) == {None: "foo"}
