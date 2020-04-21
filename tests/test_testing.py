import pytest


async def prepare():
    from buvar import context

    context.add("foobar")


@pytest.mark.asyncio
@pytest.mark.buvar_plugins("tests.test_testing")
async def test_wrapped_stage_context():
    from buvar import context, plugin

    assert context.get(str) == "foobar"
    assert context.get(plugin.Cancel)


@pytest.mark.asyncio
@pytest.mark.buvar_plugins()
async def test_wrapped_stage_context_load(buvar_load):
    from buvar import context, plugin

    await buvar_load(prepare)
    assert context.get(str) == "foobar"
    assert context.get(plugin.Cancel)
