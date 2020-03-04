import pytest


def test_run(event_loop):
    from buvar import plugin, context, ComponentLookupError

    result = plugin.stage("tests.foo_plugin", loop=event_loop)
    assert result == [{"foo": "foo"}, None, None]
    with pytest.raises(ComponentLookupError) as e:
        context.get("foo_plugin")
    assert e.value.args[1] == "foo_plugin"


def test_run_relative_out_of_packages(event_loop):
    from buvar import plugin

    with pytest.raises(ValueError):
        plugin.stage("tests.baz_plugin", loop=event_loop)


def test_run_with_loader(event_loop, mocker):
    from buvar import plugin

    async def test_plugin(load: plugin.Loader):
        pass

    plugin.stage(test_plugin)


def test_run_load_twice(event_loop):
    from buvar import plugin

    loaded = {}

    async def test_plugin(include: plugin.Loader):
        assert not loaded
        loaded[True] = True
        await include(test_plugin)

    plugin.stage(test_plugin)


def test_run_iterable(event_loop):
    from buvar import plugin

    state = {}

    async def iter_plugin():
        async def a():
            state["a"] = True

        async def b():
            state["b"] = True

        return [a(), b()]

    plugin.stage(iter_plugin, loop=event_loop)
    assert state == {"a": True, "b": True}


def test_plugin_error(event_loop):
    from buvar import plugin

    state = {}

    async def broken_plugin(teardown: plugin.Teardown):
        async def teardown_task():
            state["teardown_task"] = True

        teardown.add(teardown_task())

        raise Exception("Plugin is broken")

    with pytest.raises(Exception) as e:
        plugin.stage(broken_plugin, loop=event_loop)
        assert e.error.args == ("Plugin is broken",)
    assert state == {"teardown_task": True}


def test_cancel_staging(event_loop):
    import asyncio
    from buvar import plugin

    state = {}

    async def server_plugin(cancel: plugin.Cancel):
        async def server():
            # shutdown
            cancel.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                state["cancelled"] = True

        yield server()

    plugin.stage(server_plugin, loop=event_loop)
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
        plugin.resolve_plugin_func(lambda: None)


def test_subtask(event_loop):
    from buvar import plugin

    state = {}

    async def test_plugin(teardown: plugin.Teardown):
        state["plugin"] = True

        async def teardown_task():
            state["teardown_task"] = True

        teardown.add(teardown_task())

        async def task():
            state["task"] = True

        yield task()

    plugin.stage(test_plugin, loop=event_loop)

    assert state == {"plugin": True, "task": True, "teardown_task": True}


def test_broken_task(event_loop):
    import asyncio
    from buvar import plugin

    state = {}

    async def broken_plugin(teardown: plugin.Teardown):
        async def teardown_task():
            state["teardown_task"] = True

        teardown.add(teardown_task())

        async def task():
            await asyncio.Future()

        async def broken_task():
            raise Exception("Task is broken")

        yield task()
        yield broken_task()

    with pytest.raises(Exception) as e:
        plugin.stage(broken_plugin, loop=event_loop)
        assert e.error.args == ("Task is broken",)
    assert state == {"teardown_task": True}
