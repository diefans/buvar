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
    data = await res.json()
    assert data == {
        "foo": "bar",
        "operation": {
            "id": "get_bar",
            "method": "get",
            "parameters": [
                {"in": "query", "name": "foo", "schema": {"type": "string"}}
            ],
            "path": {
                "parameters": [
                    {"in": "path", "name": "id", "schema": {"type": "string"}}
                ],
                "url": "/bar/{id}",
            },
            "request_body": None,
            "responses": {"200": {"description": "test"}},
        },
    }

    res = await client.get("/openapi")
    assert res.status == 200
