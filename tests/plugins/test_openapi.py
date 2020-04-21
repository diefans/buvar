import pytest


@pytest.fixture
def loop(event_loop):
    return event_loop


@pytest.fixture
def buvar_config_source(buvar_config_source):
    buvar_config_source.env_prefix = ("BUVAR",)
    buvar_config_source.merge({"openapi": {"path": "tests.plugins:api.yaml"}})
    return buvar_config_source


@pytest.mark.asyncio
@pytest.mark.buvar_plugins("buvar.config", "tests.plugins.openapi")
async def test_openapi(buvar_aiohttp_app, test_client):
    client = await test_client(buvar_aiohttp_app)

    res = await client.post("/api/foo")

    assert res.status == 200
    assert await res.json() == {"foo": "bar"}

    res = await client.get("/openapi")
    assert res.status == 200
