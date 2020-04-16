import pytest


def foo():
    ...


def test_resolve_dotted_name():
    from buvar import util

    fun = util.resolve_dotted_name("dotted:name")

    assert fun() == "foobar"


def test_resolve_dotted_name_no_module():
    from buvar import util

    with pytest.raises(ModuleNotFoundError):
        util.resolve_dotted_name("nomodule:name")


def test_resolve_dotted_name_wrong_name():
    from buvar import util

    with pytest.raises(ValueError):
        util.resolve_dotted_name("nomodule:na:me")


def test_resolve_dotted_name_relative():
    from buvar import util

    func = util.resolve_dotted_name(".test_util:foo")

    assert func is foo
