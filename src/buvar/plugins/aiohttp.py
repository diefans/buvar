import aiohttp.web
import attr
import structlog

from buvar import config, context, Teardown


@attr.s(auto_attribs=True)
class AioHttpConfig:
    host: str = "0.0.0.0"
    port: int = 8080


class AccessLogger(aiohttp.abc.AbstractAccessLogger):  # noqa: R0903
    def log(self, request, response, time):  # noqa: R0201
        log = structlog.get_logger()
        log.info(
            "Access",
            remote=request.remote,
            method=request.method,
            path=request.path,
            time=time,
            status=response.status,
        )


async def plugin_app():
    context.add(
        aiohttp.web.Application(middlewares=[aiohttp.web.normalize_path_middleware()])
    )


async def plugin_client_session():
    aiohttp_client_session = context.add(aiohttp.client.ClientSession())

    teardown = context.get(Teardown)
    teardown.add(aiohttp_client_session.close())


async def plugin_server(load):
    await load(plugin_app)
    aiohttp_app = context.get(aiohttp.web.Application)

    config_source = context.get(config.ConfigSource)
    aiohttp_config = context.add(config_source.load(AioHttpConfig, "aiohttp"))

    yield aiohttp.web._run_app(  # noqa: W0212
        aiohttp_app, host=aiohttp_config.host, port=aiohttp_config.port, print=None
    )


async def plugin(load):
    await load(plugin_client_session)
    await load(plugin_server)
