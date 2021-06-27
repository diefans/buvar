import pytest


def test_forked_parent(mocker):
    import os
    from buvar import fork

    mocker.patch("os.getpid", return_value=1)
    mock_pgid = mocker.patch("os.getpgid", return_value=2)
    mock_waitid = mocker.patch("os.waitid")
    mocker.patch("os.fork", return_value=123)
    f = fork.Fork(2)
    f.run(lambda x: x)

    mock_pgid.assert_called_with(1)
    mock_waitid.assert_called_with(os.P_PGID, 2, os.WEXITED)
    assert f.children == {123}


def test_forked_child(mocker):
    from buvar import fork

    mocker.patch("os.waitid")
    mocker.patch("os.fork", return_value=0)
    f = fork.Fork(2)

    stuff_args = {}

    def stuff(a, b):
        stuff_args[a] = b

    f.run(stuff, 1, 2)
    assert stuff_args == {1: 2}


def test_forked_no_fork(mocker):
    from buvar import fork

    f = fork.Fork(1)

    stuff_args = {}

    def stuff(a, b):
        stuff_args[a] = b

    f.run(stuff, 1, 2)
    assert stuff_args == {1: 2}
