"""Create a aiohttp server task and provide the application via context."""
import aiohttp.web
import attr
import structlog

from buvar import config, context

sl = structlog.get_logger()


@attr.s(auto_attribs=True)
class AioHttpConfig:
    host: str = "0.0.0.0"
    port: int = 8080


class AccessLogger(aiohttp.abc.AbstractAccessLogger):  # noqa: R0903
    def log(self, request, response, time):  # noqa: R0201
        sl.info(
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
    aiohttp_app = context.add(
        aiohttp.web.Application(middlewares=[aiohttp.web.normalize_path_middleware()])
    )

    sl.info("Running web server", host=aiohttp_config.host, port=aiohttp_config.port)
    # return server task
    yield aiohttp.web._run_app(  # noqa: W0212
        aiohttp_app, host=aiohttp_config.host, port=aiohttp_config.port, print=None
    )
