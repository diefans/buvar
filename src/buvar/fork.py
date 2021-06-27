import abc
import contextlib
import os
import queue
import signal
import socket
import typing as t

import uritools

from buvar import plugin
from buvar.components import Components

URI = uritools.SplitResult

SocketArgs = t.Optional[t.Tuple[t.Any, ...]]


class Socket(socket.socket, metaclass=abc.ABCMeta):
    __impls__ = set()

    def __new__(cls, ref: str) -> "Socket":
        parts: URI = uritools.urisplit(ref)
        for impl_cls in cls.__impls__:
            uri_socket_args = impl_cls.create(parts)
            if uri_socket_args:
                inst_uri, *socket_args = uri_socket_args
                inst = super().__new__(impl_cls, *socket_args)
                inst.uri = inst_uri
                inst.args = socket_args
                return inst

        raise TypeError(f"No socket implementation for: {ref}", ref)

    def __init__(self, uri):
        super().__init__(*self.args)

    def __init_subclass__(cls) -> None:
        cls.__impls__.add(cls)

    @abc.abstractmethod
    def bind(cls):
        ...

    @abc.abstractclassmethod
    def create(cls, uri: URI) -> SocketArgs:
        ...

    def __hash__(self):
        return hash(self.uri)

    def __eq__(self, other):
        return isinstance(other, Socket) and self.uri == other.uri

    def __str__(self):
        return uritools.uriunsplit(self.uri)


class TCPSocket(Socket):
    @classmethod
    def create(cls, uri: URI) -> SocketArgs:
        if uri.scheme == "tcp":
            if uri.gethost() == "":
                uri = uri.transform(f"tcp://0.0.0.0:{uri.getport()}")

            return uri, socket.AF_INET, socket.SOCK_STREAM

    def bind(self):
        socket.socket.bind(self, (str(self.uri.gethost()), self.uri.getport()))


class UnixSocket(Socket):
    @classmethod
    def create(cls, uri: URI) -> SocketArgs:
        if uri.scheme == "unix":
            # resolve abs path
            ...
            return uri, socket.AF_UNIX, socket.SOCK_STREAM

    def bind(self):
        super().bind(self.uri.getpath())


class Sockets(dict):
    def __init__(self, *sockets: str):
        super().__init__((str(s), s) for s in map(Socket, sockets))

    @contextlib.contextmanager
    def bind(self):
        try:
            for s in self.values():
                s.bind()
            yield self
        finally:
            for s in self.values():
                s.close()


class Fork:
    number: int = 0
    ppid: int
    pid: int
    is_child: bool

    def __init__(self, number: int):
        self.number = number
        self.children = set()
        self.queue = queue.Queue()
        self.pid = os.getpid()
        self.ppid = os.getppid()
        self.is_child = False

    def run(
        self, func: t.Callable, *args: t.Any, **kv: t.Any
    ) -> t.Optional[t.List[t.Any]]:
        forks = len(os.sched_getaffinity(0)) if not self.number else self.number

        if forks == 1:
            return func(*args, **kv)

        for i in range(forks):
            child = os.fork()
            if child:
                self.children.add(child)
            else:
                self.pid = os.getpid()
                self.ppid = os.getppid()
                self.is_child = True
                result = func(*args, **kv)
                self.queue.put(result)

        if self.children:
            self.wait_for_children()
            result = []
            while True:
                try:
                    result.append(self.queue.get(False))
                except queue.Empty:
                    break
            return result

    def _signal_children(self, signum, frame):
        for child in self.children:
            os.kill(child, signum)

    def wait_for_children(self):
        pgid = os.getpgid(self.pid)
        signal.signal(signal.SIGINT, self._signal_children)
        signal.signal(signal.SIGHUP, self._signal_children)
        signal.signal(signal.SIGTERM, self._signal_children)
        os.waitid(os.P_PGID, pgid, os.WEXITED)


def stage(
    *plugins,
    components=None,
    loop=None,
    forks: int = 0,
    sockets: t.Optional[t.Sequence[str]] = None,
):
    if components is None:
        components = Components()

    f = components.add(Fork(forks))
    with Sockets(*sockets).bind() as s:
        # register sockets
        for name, s in s.items():
            components.add(s, name=name)

        return f.run(plugin.stage, *plugins, components=components, loop=loop)
