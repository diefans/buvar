import aiohttp.web

from buvar import plugin
from buvar.plugins.aiohttp import openapi

operation_map = openapi.OperationMap()


@operation_map.register()
async def post_foo(request):
    raise aiohttp.web.HTTPFound(
        location=request.app.router["get_bar"].url_for(id="1234")
    )


@operation_map.register()
async def get_bar(request):
    return aiohttp.web.json_response({"foo": "bar"})


async def prepare(load: plugin.Loader):
    await load("buvar.plugins.aiohttp")
    await operation_map.mount(ui=True)
