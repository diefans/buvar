import pytest


def test_run():
    from buvar import ComponentLookupError, context, plugin

    result = plugin.stage("tests.foo_plugin")
    assert result == [{"foo": "foo"}, None, None]
    with pytest.raises(ComponentLookupError) as e:
        context.get("foo_plugin")
    assert e.value.args[1] == "foo_plugin"


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

    async def test_plugin(load: plugin.Loader):
        assert not loaded
        loaded[True] = True
        await load(test_plugin)

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


def test_staging_result_ok():
    from buvar import plugin

    async def foo():
        async def foo_task():
            return "foo"

        return foo_task()

    async def bar():
        async def bar_task():
            return "bar"

        yield bar_task()

    result = plugin.stage(
        foo,
        bar,
        cancel_timeout=0.1,
    )
    assert result == ["foo", "bar"]


def test_cancel_staging():
    import asyncio

    from buvar import plugin

    async def cancel_task_plugin(cancel: plugin.Cancel):
        async def cancel_task():
            await asyncio.sleep(0)
            # shutdown
            cancel.set()
            return "cancel"

        yield cancel_task()

    async def graceful_server_plugin(cancel: plugin.Cancel):
        async def server():
            await cancel.wait()
            return "graceful_server"

        yield server()

    async def ungraceful_server_plugin():
        async def server():
            await asyncio.sleep(0)
            try:
                # INFO: wait for something
                await asyncio.Future()
            except asyncio.CancelledError:
                return "ungraceful_server"

        yield server()

    result = plugin.stage(
        cancel_task_plugin,
        graceful_server_plugin,
        ungraceful_server_plugin,
        cancel_timeout=0.1,
    )
    assert result == ["cancel", "graceful_server", "ungraceful_server"]


def test_cancelled_task(Something):
    import asyncio

    from buvar import plugin

    async def broken_plugin(cancel: plugin.Cancel):
        fut_task = asyncio.Future()

        async def cancel_task():
            await asyncio.sleep(0)
            # shutdown
            cancel.set()
            return "cancel"

        async def task():
            await fut_task

        yield cancel_task()
        yield task()

    result = plugin.stage(broken_plugin, cancel_timeout=0.1)
    assert result == [
        "cancel",
        Something(lambda x: isinstance(x, asyncio.CancelledError)),
    ]


def test_broken_task_with_cancel(Something):
    import asyncio

    from buvar import plugin

    class MyException(Exception): ...

    async def broken_plugin(cancel: plugin.Cancel):
        async def cancel_task():
            await asyncio.sleep(0)
            # shutdown
            cancel.set()
            return "cancel"

        async def broken_task():
            raise MyException("Task is broken")

        yield cancel_task()
        yield broken_task()

    result = plugin.stage(broken_plugin, cancel_timeout=0.1)
    assert result == ["cancel", Something(lambda x: isinstance(x, MyException))]


def test_signal_cancel(Something):
    import asyncio
    import os
    import signal

    from buvar import plugin

    pid = os.getpid()

    class Signals(plugin.Signals):
        def handle_usr1(self):
            self.stage.cancel.set()

    async def myplugin(cancel: plugin.Cancel):
        fut_task = asyncio.Future()

        async def cancel_task():
            await asyncio.sleep(0)
            # shutdown
            os.kill(pid, signal.SIGUSR1)
            return "cancel"

        async def task():
            await fut_task

        yield cancel_task()
        yield task()

    result = plugin.stage(myplugin, cancel_timeout=0.1, signals=Signals)
    assert result == [
        "cancel",
        Something(lambda x: isinstance(x, asyncio.CancelledError)),
    ]
