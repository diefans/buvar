import pytest


def test_tcp_socket():
    import socket
    from buvar import fork

    s = fork.Socket("tcp://:12345")
    assert s.family == socket.AF_INET
    assert s.uri.getport() == 12345
    assert str(s.uri.gethost()) == "0.0.0.0"


def test_unix_socket():
    import socket
    from buvar import fork

    s = fork.Socket("unix:///tmp/foo.sock")
    assert s.family == socket.AF_UNIX
    assert s.uri.getpath() == "/tmp/foo.sock"


def test_tcp_sockets():
    from buvar import fork

    s = fork.Sockets(
        "tcp://:12345",
        "tcp://:12345",
        "unix:///tmp/foo.sock",
    )
    assert s == {
        "tcp://0.0.0.0:12345": fork.Socket("tcp://:12345"),
        "unix:///tmp/foo.sock": fork.Socket("unix:///tmp/foo.sock"),
    }


def test_socket_not_implemented():
    from buvar import fork

    with pytest.raises(TypeError):
        fork.Socket("http://:12345")


def test_bind_tcp_socket(Anything):
    from buvar import fork

    s = fork.Socket("tcp://:0")
    s.bind()
    try:
        assert s.getsockname() == ("0.0.0.0", Anything)
    finally:
        s.close()


def test_bind_sockets(Anything):
    from buvar import fork

    with fork.Sockets("tcp://:0").bind() as sockets:
        s = next(iter(sockets.values()))
        assert s.getsockname() == ("0.0.0.0", Anything)
