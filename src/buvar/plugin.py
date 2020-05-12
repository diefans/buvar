"""Very simple plugin architecture for asyncio.

`Loader` calls prepare coroutines, which yield tasks, the `Loader` collects.
These tasks are then run until complete.

A py:obj:`buvar.components.Components` context is stacked in way, that plugins
share the same context, while tasks don't, but may access the plugin context.


    >>> loop = asyncio.get_event_loop()
    >>> state = {}
    >>> async def prepare(load: Loader):
    ...     async def some_task():
    ...         state['task'] = True
    ...         return "foo"
    ...     yield some_task()

    >>> mystage = Stage()
    >>> mystage.load(prepare)
    >>> mystage.run()
    ['foo']
    >>> assert state == {'task': True}

    >>> state = {}
    >>> stage(prepare)
    ['foo']
    >>> assert state == {'task': True}
"""
import asyncio
import collections.abc
import inspect
import itertools
import sys
import types
import typing

import structlog

from . import context, util

PLUGIN_FUNCTION_NAME = "prepare"


sl = structlog.get_logger()


class Cancel(asyncio.Event):
    pass


class Teardown:
    """A collection of teardown tasks."""

    def __init__(self):
        self.tasks = []

    def add(self, task):
        self.tasks.append(task)

    def __iter__(self):
        """We teardown in the reverse order of registration."""
        return reversed(self.tasks)

    async def wait(self):
        await asyncio.gather(*self)


class Loader:
    """Load plugins and collect tasks."""

    def __init__(self):
        self._tasks = {}

    @property
    def tasks(self):
        return iter(itertools.chain(*self._tasks.values()))

    async def __call__(self, *plugins):
        """Hook the plugin from another plugin.

        The plugin may return an awaitable, an iterable of awaitables or an
        asyncgenerator of awaitables.

        The plugin function may use annotated arguments, which are provided by
        the actual stage context.

        :param plugins: the plugin to load
        :type plugins: list of callables
        """
        for plugin in plugins:
            plugin = resolve_plugin_func(plugin, caller=sys._getframe(1))
            if plugin not in self._tasks:
                sl.info("Plugin", plugin=util.fqdn(plugin))
                # mark plugin as loaded for recursive circular stuff
                self._tasks[plugin] = []
                # load plugin
                args = collect_plugin_args(plugin)
                try:
                    result = plugin(**args)
                except TypeError as ex:
                    raise TypeError(*ex.args, plugin.__module__, plugin.__name__)
                callables = [fun async for fun in generate_async_result(result)]
                self._tasks[plugin].extend(callables)


class Stage:
    """Stage manages the context stack while running each phase of the machinery.

    The stack typically has four layers:

    1. the default import time context

    2. the components context passed to the stage

    3. stage management context, e.g. Cancel, Teardown, Loader

    4. the shared plugin preparation context
    """

    def __init__(self, components=None, loop=None):
        self.loop = loop or asyncio.get_event_loop()
        self.context = (
            context.current_context()
            .push(*(components.stack if components else ()))
            .push()
        )
        # provide basic components
        self.cancel = self.context.add(Cancel(loop=self.loop))
        self.teardown = self.context.add(Teardown())
        self.loader = self.context.add(Loader())

        self.context = self.context.push()

    def load(self, *plugins):
        sl.info("Loading plugins")

        @context.run_child(self.context)
        def _load():
            self.loop.run_until_complete(self.loader(*plugins))

        _load()

    def run_tasks(self):
        sl.info("Running tasks", tasks=self.loader.tasks)

        @context.run_child(self.context)
        def _run_tasks():
            return self.loop.run_until_complete(
                run(tasks=self.loader.tasks, evt_cancel=self.cancel)
            )

        return _run_tasks()

    def run_teardown(self):
        sl.info("Teardown", tasks=self.teardown.tasks)
        self.loop.run_until_complete(self.teardown.wait())

    def run(self, *plugins):
        """Start the asyncio process by bootstrapping the root plugins.

        We have a three phase setup:

        1. run plugin hooks, to register arbitrary stuff and mainly gather a set of
        asyncio tasks for the second phase

        2. run all registered tasks together until complete

        3. teardown
        """
        try:
            # stage 1: bootstrap plugins
            self.load(*plugins)

            # stage 2: run main task and collect teardown tasks
            return self.run_tasks()
        finally:
            # stage 3: teardown
            self.run_teardown()


def stage(*plugins, components=None, loop=None):
    if loop is None:
        loop = asyncio.get_event_loop()

    stage = Stage(components=components, loop=loop)
    return stage.run(*plugins)


async def run(tasks, *, evt_cancel=None):
    if evt_cancel is None:
        evt_cancel = context.add(Cancel())

    # we elevate context stack for tasks
    factory = context.set_task_factory()
    try:
        fut_tasks = asyncio.gather(*map(asyncio.create_task, tasks))
    finally:
        factory.reset()

    # stop staging if we finish in any way
    fut_tasks.add_done_callback(lambda _: evt_cancel.set())

    # wait for exit
    await evt_cancel.wait()

    if not fut_tasks.done():
        # we were explicitelly stopped by cancel event
        fut_tasks.cancel()
        try:
            await fut_tasks
        except asyncio.CancelledError:
            # silence our shutdown
            pass
    else:
        return fut_tasks.result()


def collect_plugin_args(plugin):
    hints = typing.get_type_hints(plugin)
    args = {name: context.get(cls) for name, cls in hints.items()}
    return args


def resolve_plugin_func(
    plugin,
    *,
    function_name=PLUGIN_FUNCTION_NAME,
    caller: typing.Union[types.FrameType, int] = 0,
):
    plugin = util.resolve_dotted_name(
        plugin, caller=(caller + 1) if isinstance(caller, int) else caller
    )
    if inspect.ismodule(plugin):
        # apply default name
        plugin = getattr(plugin, function_name)

    if not (inspect.iscoroutinefunction(plugin) or inspect.isasyncgenfunction(plugin)):
        raise ValueError(f"{plugin} must a coroutine or an async generator.")

    return plugin


async def generate_async_result(fun_result):
    """Create an async generator out of any result."""
    if inspect.isasyncgen(fun_result):
        async for item in fun_result:
            yield item
    else:
        result = await fun_result
        if isinstance(result, collections.abc.Iterable):
            for item in result:
                yield item
        elif result is not None:
            yield result
