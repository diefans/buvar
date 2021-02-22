import pytest


def test_run(event_loop):
    from buvar import plugin, context, ComponentLookupError

    result = plugin.stage("tests.foo_plugin", loop=event_loop)
    assert result == [{"foo": "foo"}, None, None]
    with pytest.raises(ComponentLookupError) as e:
        context.get("foo_plugin")
    assert e.value.args[1] == "foo_plugin"


def test_run_task_factory(event_loop):
    import asyncio
    from buvar import plugin, context

    async def prepare():
        async def task():
            async def _sub1():
                context.add("foo")
                await asyncio.sleep(0)
                assert "foo" == context.get(str)

            async def _sub2():
                context.add("bar")
                await asyncio.sleep(0)
                assert "bar" == context.get(str)

            await asyncio.gather(
                asyncio.create_task(_sub1()), asyncio.create_task(_sub2())
            )

        yield task()

    result = plugin.stage(prepare, loop=event_loop)


def test_run_relative_out_of_packages(event_loop):
    from buvar import plugin

    with pytest.raises(ImportError):
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
        fut_task = asyncio.Future()

        async def task():
            await fut_task

        async def teardown_task():
            state["teardown_task"] = True
            fut_task.cancel()

            try:
                await fut_task
            except asyncio.CancelledError:
                ...

        teardown.add(teardown_task())

        async def broken_task():
            raise Exception("Task is broken")

        yield task()
        yield broken_task()

    with pytest.raises(Exception) as e:
        plugin.stage(broken_plugin, loop=event_loop)
        assert e.error.args == ("Task is broken",)
    assert state == {"teardown_task": True}


def test_stage_components():
    import asyncio
    from buvar import plugin, components, context

    async def test_plugin(load: plugin.Loader):
        assert context.get(str) == "foo"
        context.add("bar", name="bar")

        async def task1():
            assert context.get(str, name="bar") == "bar"
            asyncio.sleep(0.02)
            context.add("task1", name="bar")
            asyncio.sleep(0.01)
            assert context.get(str, name="bar") == "task1"

        async def task2():
            assert context.get(str, name="bar") == "bar"
            asyncio.sleep(0.01)
            context.add("task2", name="bar")
            asyncio.sleep(0.02)
            assert context.get(str, name="bar") == "task2"

        yield task1()
        yield task2()

    cmps = components.Components()
    cmps.add("foo")

    plugin.stage(test_plugin, components=cmps)
