import aiohttp.web
import structlog

from buvar import context

log = structlog.get_logger()
routes = aiohttp.web.RouteTableDef()


@routes.get("/")
async def index(request):
    return aiohttp.web.json_response({"hello": "world"})


async def plugin(include):
    await include(".server")
    app = context.get(aiohttp.web.Application)
    app.add_routes(routes)
