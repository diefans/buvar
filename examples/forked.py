import aiohttp.web
from buvar_aiohttp import AioHttpConfig

from buvar import context, di, fork, plugin


async def hello(request):
    return aiohttp.web.Response(body=b"Hello, world")


async def prepare_aiohttp(load: plugin.Loader):
    await load("buvar_aiohttp")

    app = await di.nject(aiohttp.web.Application)
    app.router.add_route("GET", "/", hello)


context.add(AioHttpConfig(host="0.0.0.0", port=5678))

fork.stage(prepare_aiohttp, forks=0, sockets=["tcp://:5678"])
