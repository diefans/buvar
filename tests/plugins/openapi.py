import aiohttp.web

from buvar import plugin, di
from buvar.plugins.aiohttp import openapi, json

operation_map = openapi.OperationMap()


@operation_map.register()
async def post_foo(request):
    raise aiohttp.web.HTTPFound(
        location=request.app.router["get_bar"].url_for(id="1234")
    )


@operation_map.register()
async def get_bar(request):
    op = await di.nject(openapi.Operation, request=request)
    return json.response({"foo": "bar", "operation": op})


async def prepare(load: plugin.Loader):
    await load("buvar.plugins.aiohttp.openapi", "buvar.plugins.aiohttp.json")
    await operation_map.mount(ui=True)
