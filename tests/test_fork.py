import pytest


def test_forked_parent(mocker):
    from buvar import fork

    mock_waitpid = mocker.patch("os.waitpid")
    mock_fork = mocker.patch("os.fork", return_value=123)
    f = fork.Fork(2)
    f.run(lambda x: x)
    mock_waitpid.assert_called_with(123, 0)


def test_forked_child(mocker):
    from buvar import fork

    mock_waitpid = mocker.patch("os.waitpid")
    mock_fork = mocker.patch("os.fork", return_value=0)
    f = fork.Fork(2)

    stuff_args = {}

    def stuff(a, b):
        stuff_args[a] = b

    f.run(stuff, 1, 2)
    assert stuff_args == {1: 2}


def test_forked_no_fork(mocker):
    from buvar import fork

    mock_waitpid = mocker.patch("os.waitpid")
    mock_fork = mocker.patch("os.fork", return_value=0)
    f = fork.Fork(1)

    stuff_args = {}

    def stuff(a, b):
        stuff_args[a] = b

    f.run(stuff, 1, 2)
    assert stuff_args == {1: 2}
