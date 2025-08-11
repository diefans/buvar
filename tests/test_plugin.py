import pytest


def test_run():
    from buvar import ComponentLookupError, context, plugin

    result = plugin.stage("tests.foo_plugin")
    assert result == [{"foo": "foo"}, None, None]
    with pytest.raises(ComponentLookupError) as e:
        context.get("foo_plugin")
    assert e.value.args[1] == "foo_plugin"


def test_run_task_factory():
    import asyncio

    from buvar import context, plugin

    async def prepare():
        context_size = len(context.current_context().stack)

        async def task():
            async def _sub1():
                assert len(context.current_context().stack) == context_size + 2
                context.add("foo")
                await asyncio.sleep(0)
                assert "foo" == context.get(str)

            async def _sub2():
                assert len(context.current_context().stack) == context_size + 2
                context.add("bar")
                await asyncio.sleep(0)
                assert "bar" == context.get(str)

            task_1 = asyncio.create_task(_sub1())
            task_2 = asyncio.create_task(_sub2())
            await asyncio.gather(task_1, task_2)

        yield task()

    result = plugin.stage(prepare)


def test_run_relative_out_of_packages():
    from buvar import plugin

    with pytest.raises(ImportError):
        plugin.stage("tests.baz_plugin")


def test_run_with_loader():
    from buvar import plugin

    async def test_plugin(load: plugin.Loader):
        pass

    plugin.stage(test_plugin)


def test_run_load_twice():
    from buvar import plugin

    loaded = {}

    async def test_plugin(include: plugin.Loader):
        assert not loaded
        loaded[True] = True
        await include(test_plugin)

    plugin.stage(test_plugin)


def test_run_iterable():
    from buvar import plugin

    state = {}

    async def iter_plugin():
        async def a():
            state["a"] = True

        async def b():
            state["b"] = True

        return [a(), b()]

    plugin.stage(iter_plugin)
    assert state == {"a": True, "b": True}


def test_plugin_error():
    from buvar import plugin

    state = {}

    async def broken_plugin(teardown: plugin.Teardown):
        async def teardown_task():
            state["teardown_task"] = True

        teardown.add(teardown_task())

        raise Exception("Plugin is broken")

    with pytest.raises(Exception) as e:
        plugin.stage(broken_plugin)
        assert e.error.args == ("Plugin is broken",)
    assert state == {"teardown_task": True}


def test_cancel_staging():
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

    plugin.stage(server_plugin)
    assert state == {"cancelled": True}


def test_resolve_plugin_not_async():
    from buvar import plugin

    with pytest.raises(ValueError):
        plugin.resolve_plugin_func(lambda: None)


def test_subtask():
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

    plugin.stage(test_plugin)

    assert state == {"plugin": True, "task": True, "teardown_task": True}


def test_broken_task():
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
        plugin.stage(broken_plugin)
        assert e.error.args == ("Task is broken",)
    assert state == {"teardown_task": True}


def test_stage_components():
    import asyncio

    from buvar import components, context, plugin

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
