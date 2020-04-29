"""API first initiative.

At the moment this is a poor man's approach:

- only operations are mapped to routes


TODO

- schema validation
- auth
"""
import importlib.resources
import string
import typing
import urllib.parse

import aiofile
import aiohttp.web
import attr
import cached_property
import prance
import structlog

from buvar import config, context, di, plugin

from . import json

sl = structlog.get_logger()


@attr.s(auto_attribs=True)
class OpenApiConfig(config.Config, section="openapi"):
    path: str

    @cached_property.cached_property
    async def spec(self):
        module, _, path = self.path.partition(":")
        with importlib.resources.path(module, path) as path:
            async with aiofile.AIOFile(path) as afp:
                parser = prance.ResolvingParser(spec_string=await afp.read())
                return parser.specification


@attr.s(auto_attribs=True)
class Path:
    url: str
    parameters: typing.Optional[typing.List[typing.Dict]]


@attr.s(auto_attribs=True)
class Operation:
    id: str
    path: Path
    method: str
    parameters: typing.Optional[typing.List[typing.Dict]]
    responses: typing.Any
    request_body: typing.Any

    def add(self, routes: aiohttp.web.RouteTableDef, func):
        method = getattr(routes, self.method)
        method(self.path.url, name=self.id)(func)
        context.add(self, name=self.id)

    @classmethod
    async def adapt(cls, request: aiohttp.web.Request) -> "Operation":
        return context.get(cls, name=request.match_info.route.name)


def resolve_operations(openapi_spec):
    for url, methods in openapi_spec["paths"].items():
        path_parameters = methods.get("parameters")
        path = Path(url=url, parameters=path_parameters)
        for method, op in methods.items():
            if "parameters" == method:
                continue
            if "operationId" not in op:
                sl.warn("Operation lacks operationId", path=path, operation=op)
                continue
            operation = Operation(
                id=op["operationId"],
                path=path,
                method=method.lower(),
                parameters=op.get("parameters"),
                responses=op.get("responses"),
                request_body=op.get("requestBody"),
            )
            sl.info("Operation", operation=operation)
            yield operation


def get_api_base(openapi_spec):
    for server in openapi_spec["servers"]:
        url = urllib.parse.urlparse(server["url"])
        return url.path


class OperationMapIncomplete(Exception):
    ...


class OperationMap:
    handlers: typing.Dict

    def __init__(self, *, allow_incomplete=False):
        self.handlers = {}
        self.allow_incomplete = allow_incomplete

    def register(self, operation_id=None):
        def _reg(func):
            op_id = operation_id if operation_id is not None else func.__name__
            if op_id in self.handlers:
                sl.warn(
                    "Operation already mapped",
                    operation_id=op_id,
                    func=self.handlers[op_id],
                )
            self.handlers[op_id] = func
            return func

        return _reg

    def create_subapp(self, spec, *, app=None):
        if app is None:
            app = aiohttp.web.Application()

        routes = aiohttp.web.RouteTableDef()
        # create subapp or prepend servers
        operations = {op.id: op for op in resolve_operations(spec)}
        for operation_id, func in self.handlers.items():
            try:
                operation = operations.pop(operation_id)
            except IndexError:
                sl.info("Operation not in API", operation=operation)
            else:
                operation.add(routes, func)

        app.add_routes(routes)
        if operations:
            if self.allow_incomplete:
                sl.warn("Not all operations mapped", unmapped=operations)
            else:
                sl.error("Not all operations mapped", unmapped=operations)
                raise OperationMapIncomplete(operations)
        return app

    async def mount(
        self,
        *,
        spec: typing.Optional[typing.Dict] = None,
        app: typing.Optional[aiohttp.web.Application] = None,
        ui: typing.Union[str, bool] = False,
    ):

        if spec is None:
            config = await di.nject(OpenApiConfig)
            spec = await config.spec

        if app is None:
            app = await di.nject(aiohttp.web.Application)

        subapp = self.create_subapp(spec)
        app.add_subapp(get_api_base(spec), subapp)

        if ui:
            openapi_routes = OpenApiRouteTableDef()
            openapi_routes.get("/spec", name=BUVAR_OPENAPI_SPEC_ROUTE)(get_openapi_spec)
            openapi_routes.get("/", name=BUVAR_OPENAPI_ROUTE)(get_openapi)
            openapi_app = OpenApiApplication()
            openapi_app.add_routes(openapi_routes)
            app.add_subapp(BUVAR_OPENAPI_PATH if ui is True else ui, openapi_app)


BUVAR_OPENAPI_PATH = "/openapi"
BUVAR_OPENAPI_SPEC_ROUTE = "buvar_openapi_spec"
BUVAR_OPENAPI_ROUTE = "buvar_openapi"


async def get_openapi_spec(request):
    config = await di.nject(OpenApiConfig)
    return json.response(await config.spec)


async def get_openapi(request):
    with importlib.resources.path("buvar.plugins.aiohttp", "openapi.html") as path:
        async with aiofile.AIOFile(path) as afp:
            text = string.Template(await afp.read()).substitute(
                openapi_spec=request.app.router[BUVAR_OPENAPI_SPEC_ROUTE].url_for()
            )
            return aiohttp.web.Response(text=text, content_type="text/html")


class OpenApiRouteTableDef(aiohttp.web.RouteTableDef):
    ...


class OpenApiApplication(aiohttp.web.Application):
    ...


async def prepare(load: plugin.Loader):
    # just load aiohttp
    await load(".")
    di.register(Operation.adapt)
