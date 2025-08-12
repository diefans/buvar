import pytest


@pytest.mark.asyncio
async def test_tasks_with_context_child():
    import asyncio

    from buvar import context

    context.add("foo")
    context.add(123)

    async def task_1():
        await asyncio.sleep(0.02)
        context.add("bar")
        await asyncio.sleep(0.01)
        assert context.get(str) == "bar"
        assert context.get(int) == 123

    async def task_2():
        await asyncio.sleep(0.01)
        context.add("baz")
        await asyncio.sleep(0.02)
        assert context.get(str) == "baz"
        assert context.get(int) == 123

    with context.child():
        fut_1 = asyncio.create_task(task_1())

    with context.child():
        fut_2 = asyncio.create_task(task_2())

    await fut_1
    await fut_2

    assert context.get(str) == "foo"


@pytest.mark.asyncio
async def test_tasks_context_auto_stacking():
    import asyncio
    from typing import cast

    from buvar import context

    context.set_task_factory()

    try:
        context.add("foo")
        context.add(123)

        context_size = len(context.current_context().stack)

        async def task_1():
            assert len(context.current_context().stack) == context_size + 1
            await asyncio.sleep(0.02)
            context.add("bar")
            await asyncio.sleep(0.01)
            assert context.get(str) == "bar"
            assert context.get(int) == 123

        async def task_2():
            assert len(context.current_context().stack) == context_size + 1
            await asyncio.sleep(0.01)
            context.add("baz")
            await asyncio.sleep(0.02)
            assert context.get(str) == "baz"
            assert context.get(int) == 123

        fut_1 = asyncio.create_task(task_1())
        fut_2 = asyncio.create_task(task_2())

        await fut_1
        await fut_2
    finally:
        factory = asyncio.get_event_loop().get_task_factory()
        assert factory
        factory = cast(context.StackingTaskFactory, factory)
        factory.reset()
        assert asyncio.get_event_loop().get_task_factory() is None


def test_global_context_child():
    from buvar import context

    context.add("foo")
    context.add(123)
    with context.child():
        context.add("bar")
        assert context.get(str) == "bar"
        assert context.get(int) == 123
    assert context.get(str) == "foo"
