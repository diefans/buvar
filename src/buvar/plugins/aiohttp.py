import aiohttp.web
import attr
import structlog

from buvar import config, context


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


async def plugin():
    config_source = context.get(config.ConfigSource)
    aiohttp_config = config_source.load(AioHttpConfig, "aiohttp")
    context.add(aiohttp_config)

    aiohttp_app = aiohttp.web.Application(
        middlewares=[aiohttp.web.normalize_path_middleware()]
    )
    context.add(aiohttp_app)

    yield aiohttp.web._run_app(  # noqa: W0212
        aiohttp_app, host=aiohttp_config.host, port=aiohttp_config.port, print=None
    )
