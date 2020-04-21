import pytest


# running in manylinux docker
# the loop fixture in buvar.testing seem to have no effect
@pytest.fixture
def loop(event_loop):
    return event_loop


@pytest.mark.asyncio
@pytest.mark.buvar_plugins()
async def test_app_dummy(buvar_aiohttp_app, test_client):
    import aiohttp.web

    async def hello(request):
        return aiohttp.web.Response(body=b"Hello, world")

    buvar_aiohttp_app.router.add_route("GET", "/", hello)

    client = await test_client(buvar_aiohttp_app)
    resp = await client.get("/")
    assert "Hello, world" == await resp.text()
