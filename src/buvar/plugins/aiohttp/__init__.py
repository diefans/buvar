import socket
import typing

import aiohttp.web
import attr
from buvar import plugin, config, context
import structlog

try:
    from ssl import SSLContext
except ImportError:  # pragma: no cover
    SSLContext = typing.Any  # type: ignore


@attr.s(auto_attribs=True)
class AioHttpConfig:
    host: typing.Optional[str] = None
    port: typing.Optional[int] = None
    path: typing.Optional[str] = None
    sock: typing.Optional[socket.socket] = None
    shutdown_timeout: float = 60.0
    ssl_context: typing.Optional[SSLContext] = None
    backlog: int = 128
    handle_signals: bool = False


class AccessLogger(aiohttp.abc.AbstractAccessLogger):  # noqa: R0903
    def log(self, request, response, time):  # noqa: R0201
        log = structlog.get_logger()
        log.info(
            "Access",
            remote=request.remote,
            method=request.method,
            content_type=request.content_type,
            rx=request.content_length,
            tx=response.content_length,
            path=request.path,
            time=time,
            status=response.status,
        )


async def prepare_app():
    context.add(
        aiohttp.web.Application(middlewares=[aiohttp.web.normalize_path_middleware()])
    )


async def prepare_client_session(teardown: plugin.Teardown):
    aiohttp_client_session = context.add(aiohttp.client.ClientSession())

    teardown.add(aiohttp_client_session.close())


async def prepare_server(load: plugin.Loader):
    await load(prepare_app)
    aiohttp_app = context.get(aiohttp.web.Application)

    config_source = context.get(config.ConfigSource)
    aiohttp_config = context.add(config_source.load(AioHttpConfig, "aiohttp"))

    yield aiohttp.web._run_app(  # noqa: W0212
        aiohttp_app, **attr.asdict(aiohttp_config), print=None
    )


async def prepare(load: plugin.Loader):
    await load(prepare_client_session)
    await load(prepare_server)
