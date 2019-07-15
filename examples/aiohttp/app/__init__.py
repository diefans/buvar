from __future__ import annotations

import typing

import aiohttp.web
import attr

# why not use something sane?
import orjson

from buvar import context, di

routes = aiohttp.web.RouteTableDef()


def orjson_default(obj):
    if hasattr(obj, "__json__"):
        return obj.__json__()
    else:
        return obj


def json_response(
    data: typing.Any,
    status: int = 200,
    reason: typing.Optional[str] = None,
    headers: aiohttp.web_response.LooseHeaders = None,
) -> aiohttp.web.Response:
    body = orjson.dumps(data, default=orjson_default)
    return aiohttp.web.Response(
        body=body,
        status=status,
        reason=reason,
        headers=headers,
        content_type="application/json",
    )


@di.register
@attr.s(auto_attribs=True)
class Something:
    component: SomeComponent
    foo: str
    bar: float = None

    def __json__(self):
        return attr.asdict(self)


@di.register
class SomeService:
    def __init__(self, request: aiohttp.web.Request, something: Something = None):
        # something gets temporarily resolved
        self.request = request
        self.something = something

    def __json__(self):
        return self.something


@attr.s(auto_attribs=True)
class SomeComponent:
    foo: str
    bar: str = None

    def __json__(self):
        return attr.asdict(self)


@routes.get("/")
async def index(request):
    # we need to define a string, since `foo` has no default in `Something`
    service = await di.nject(SomeService, somestring="bar")
    assert service.something.foo == "bar"

    # but a named string is preferred
    service = await di.nject(SomeService, somestring="bar", foo="foo")
    assert service.something.foo == "foo"
    assert service.request is request
    assert service.something.component is context.get(SomeComponent)

    return json_response({"hello": "world", "something": service})


async def plugin(include):
    await include(".server")
    app = context.get(aiohttp.web.Application)
    app.add_routes(routes)
    context.add(SomeComponent(foo="bar", bar="baz"))
