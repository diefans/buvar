import pytest


@pytest.mark.parametrize(
    "src, dest",
    [
        ({"a": "foobar", "b": "1"}, {"a": "foobar", "b": 1}),
        ({"a": "str"}, {"a": "str", "b": None}),
    ],
)
def test_attrs_optional(src, dest):
    import typing
    import attr
    from buvar.plugins import attrs

    @attr.s(auto_attribs=True, kw_only=True)
    class Foo:
        a: str
        b: typing.Optional[int]

    foo = attrs.structure(src, Foo)
    assert attrs.unstructure(foo) == dest


@pytest.mark.parametrize(
    "src, dest",
    [
        ({"a": "foobar", "b": "1"}, {"a": "foobar", "b": 1}),
        ({"a": "str"}, {"a": "str", "b": 1}),
    ],
)
def test_attrs_optional_default(src, dest):
    import typing
    import attr
    from buvar.plugins import attrs

    @attr.s(auto_attribs=True, kw_only=True)
    class Foo:
        a: str
        b: typing.Optional[int] = 1

    foo = attrs.structure(src, Foo)
    assert attrs.unstructure(foo) == dest
