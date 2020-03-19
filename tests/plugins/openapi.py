import aiohttp.web
from buvar import context, di, plugin
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
    openapi_config = await di.nject(openapi.OpenApiConfig)

    spec = await openapi_config.spec
    app = context.get(aiohttp.web.Application)
    app._client_max_size = 0
    operation_map.mount_subapp(spec, app)
