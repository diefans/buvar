import pytest


@pytest.fixture
def cmps():
    from buvar import Components

    cmps = Components()
    return cmps


@pytest.fixture(autouse=True)
def no_elevated_context(mocker, cmps):
    mocker.patch("buvar.plugin.context.push", side_effect=lambda *stack: cmps)


def test_run(event_loop, cmps):
    from buvar import plugin, components

    result = plugin.run("tests.foo_plugin", components=cmps, loop=event_loop)
    assert result == [{"foo": "foo"}, None, None]
    with pytest.raises(components.ComponentLookupError) as e:
        cmps.get("foo_plugin")
    assert e.value.args[1] == "foo_plugin"


def test_run_relative_out_of_packages(event_loop):
    from buvar import plugin

    with pytest.raises(ValueError):
        plugin.run("tests.baz_plugin", loop=event_loop)


def test_run_get_event_loop(event_loop, mocker):
    from buvar import plugin

    mocker.patch.object(plugin.asyncio, "get_event_loop").return_value = event_loop

    async def test_plugin():
        pass

    plugin.run(test_plugin)


def test_run_load_twice(event_loop):
    from buvar import plugin

    loaded = {}

    async def test_plugin(include):
        assert not loaded
        loaded[True] = True
        await include(test_plugin)

    plugin.run(test_plugin)


def test_run_iterable(event_loop):
    from buvar import plugin

    state = {}

    async def iter_plugin():
        async def a():
            state["a"] = True

        async def b():
            state["b"] = True

        return [a(), b()]

    plugin.run(iter_plugin, loop=event_loop)
    assert state == {"a": True, "b": True}


def test_plugin_error(event_loop):
    from buvar import plugin, context

    state = {}

    async def broken_plugin():
        async def teardown_task():
            state["teardown_task"] = True

        teardown = context.get(plugin.Teardown)
        teardown.add(teardown_task())

        raise Exception("Plugin is broken")

    with pytest.raises(Exception) as e:
        plugin.run(broken_plugin, loop=event_loop)
        assert e.error.args == ("Plugin is broken",)
    assert state == {"teardown_task": True}


def test_cancel_staging(event_loop, cmps):
    import asyncio
    from buvar import plugin

    state = {}

    async def server_plugin():
        cancel_staging = cmps.get(plugin.CancelStaging)

        async def server():
            # shutdown
            cancel_staging.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                state["cancelled"] = True

        yield server()

    plugin.run(server_plugin, components=cmps, loop=event_loop)
    assert state == {"cancelled": True}


def test_resolve_dotted_name():
    from buvar import plugin

    fun = plugin.resolve_dotted_name("dotted:name")

    assert fun() == "foobar"


def test_resolve_dotted_name_no_module():
    from buvar import plugin

    with pytest.raises(ModuleNotFoundError):
        plugin.resolve_dotted_name("nomodule:name")


def test_resolve_dotted_name_wrong_name():
    from buvar import plugin

    with pytest.raises(ValueError):
        plugin.resolve_dotted_name("nomodule:na:me")


def test_resolve_plugin_not_async(event_loop):
    from buvar import plugin

    with pytest.raises(ValueError):
        plugin.resolve_plugin(lambda: None)


def test_subtask(event_loop, cmps):
    from buvar import plugin, context

    state = {}

    async def test_plugin():
        state["plugin"] = True

        async def teardown_task():
            state["teardown_task"] = True

        teardown = context.get(plugin.Teardown)
        teardown.add(teardown_task())

        async def task():
            state["task"] = True

        yield task()

    plugin.run(test_plugin, components=cmps, loop=event_loop)

    assert state == {"plugin": True, "task": True, "teardown_task": True}


def test_broken_task(event_loop):
    import asyncio
    from buvar import plugin, context

    state = {}

    async def broken_plugin():
        async def teardown_task():
            state["teardown_task"] = True

        teardown = context.get(plugin.Teardown)
        teardown.add(teardown_task())

        async def task():
            await asyncio.Future()

        async def broken_task():
            raise Exception("Task is broken")

        yield task()
        yield broken_task()

    with pytest.raises(Exception) as e:
        plugin.run(broken_plugin, loop=event_loop)
        assert e.error.args == ("Task is broken",)
    assert state == {"teardown_task": True}
