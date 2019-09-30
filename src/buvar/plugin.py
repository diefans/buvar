"""Very simple plugin architecture for asyncio.

    >>> components = Components()
    >>> loop = asyncio.get_event_loop()
    >>> state = {}
    >>> async def plugin(load):
    ...     async def some_task():
    ...         state['task'] = True
    ...     yield some_task()


    >>> stages = Staging(components=components, loop=loop)
    >>> load = next(stages)
    >>> load(plugin)

    >>> # wait for main task to finish
    >>> tasks_results = next(stages)

    >>> # finsh
    >>> next(stages, None)

    >>> assert state == {'task': True}


    >>> stages = Staging(plugin, components=components, loop=loop)
    >>> for stage in stages:
    ...     pass
"""
import asyncio
import collections
import collections.abc
import contextlib
import importlib
import inspect
import itertools

import structlog

from . import context
from .components import Components

PLUGIN_FUNCTION_NAME = "plugin"


sl = structlog.get_logger()


class Tasks(collections.OrderedDict):
    pass


class MainTaskFinished(asyncio.Event):
    pass


class PluginsLoaded(asyncio.Event):
    pass


class CancelMainTask(asyncio.Event):
    pass


class Bootstrap:
    """Maintain the plugin loading state."""

    def __init__(self, *, components=None, loop=None):
        self.loop = loop or asyncio.get_event_loop()
        self.components = components if components is not None else Components()

        # set task factory to serve our components context
        self.task_factory = context.set_task_factory(self.components, loop=self.loop)

        # a collection of all tasks to run
        self.collected_tasks = self.components.add(Tasks())
        self.evt_plugins_loaded = self.components.add(PluginsLoaded(loop=self.loop))

        # schedule the main task, which waits until all plugins are loaded
        self.fut_main_task = asyncio.ensure_future(self._run_tasks(), loop=self.loop)
        self.fut_cancel_main_task = asyncio.ensure_future(
            self._cancel_main_task(), loop=self.loop
        )

        self.evt_cancel_main_task = self.components.add(CancelMainTask(loop=self.loop))
        self.evt_main_task_finished = self.components.add(
            MainTaskFinished(loop=self.loop)
        )

    async def _cancel_main_task(self):
        try:
            await self.evt_cancel_main_task.wait()
        except asyncio.CancelledError:
            pass
        else:
            self.fut_main_task.cancel()
            # await self.fut_main_task

    async def include(self, plugin):
        """Hook the plugin from another plugin.

        The plugin may return an awaitable, an iterable of awaitable or an
        asyncgenerator of awaitables.

        :param plugin: the plugin to load
        :type plugin: a callable which may have one argument, receiving the
        include callback
        """
        plugin = resolve_plugin(plugin)
        if plugin not in self.collected_tasks:
            # mark plugin as loaded for recursive circular stuff
            self.collected_tasks[plugin] = []
            # load plugin
            spec = inspect.getfullargspec(plugin)
            result = plugin(self.include) if len(spec.args) == 1 else plugin()
            callables = [fun async for fun in generate_async_result(result)]
            self.collected_tasks[plugin].extend(callables)

    def load(self, plugin):
        """Load a plugin."""
        try:
            self.loop.run_until_complete(self.include(plugin))
        except Exception as ex:  # noqa: E722
            # if a plugin raises an error, we cancel the scheduled main task
            import traceback

            sl.error(
                "Error while loading plugins",
                exception=ex,
                traceback=traceback.format_exc(),
            )
            # cancel prepared main task
            self.fut_main_task.cancel()
            self.loop.run_until_complete(self.fut_main_task)
            raise

    @contextlib.contextmanager
    def run(self):
        """Run all collected tasks on context exit."""
        try:
            yield self.fut_main_task
        finally:
            self.evt_plugins_loaded.set()

    @property
    def collected_tasks_list(self):
        collected_tasks = list(itertools.chain(*self.collected_tasks.values()))
        return collected_tasks

    async def _run_tasks(self):
        # we wait for plugin loading completed
        try:
            await self.evt_plugins_loaded.wait()
        except asyncio.CancelledError:
            # stop waiting to cancel
            self.fut_cancel_main_task.cancel()
            await self.fut_cancel_main_task
            # we were in plugin loading stage
            # we cancel unawaited tasks
            for task in self.collected_tasks_list:
                if inspect.iscoroutine(task):
                    task.close()
                else:
                    task.cancel()

        # elevate the context
        self.task_factory.enable_stacking()

        # run all tasks together
        # we send them into background and gather their results
        tasks = [
            asyncio.ensure_future(async_gen_to_list(task), loop=self.loop)
            for task in self.collected_tasks_list
        ]

        try:
            # we run until all tasks have completed
            tasks_results = await asyncio.shield(
                asyncio.gather(*tasks, return_exceptions=True, loop=self.loop),
                loop=self.loop,
            )
        except asyncio.CancelledError:
            # stop all tasks
            for task in tasks:
                if not task.done():
                    task.cancel()
            tasks_results = await asyncio.gather(
                *tasks, return_exceptions=True, loop=self.loop
            )

        self.evt_main_task_finished.set()
        self.fut_cancel_main_task.cancel()
        await self.fut_cancel_main_task
        return tasks_results


class Teardown:
    """A collection of teardown tasks."""

    def __init__(self):
        self.tasks = []

    def add(self, task):
        self.tasks.append(task)

    def __iter__(self):
        """We teardown in the reverse order of registration."""
        return reversed(self.tasks)


class Staging:
    """Generate all stages to run an application."""

    def __init__(self, *plugins, components=None, loop=None):
        self.components = components if components is not None else Components()
        self.loop = loop or asyncio.get_event_loop()

        # provide a collection for teardown tasks
        self.teardown = self.components.add(Teardown())

        self.bootstrap = self.components.add(
            Bootstrap(components=components, loop=loop)
        )
        self.plugins = set(plugins)

        def iterator():
            # stage 1: bootstrap plugins
            with self.bootstrap.run() as fut_main_task:
                for plugin in self.plugins:
                    self.bootstrap.load(plugin)
                # we yield load to additionally load arbitrary stuff, after standard
                # plugin loading
                yield self.bootstrap.load

            # stage 2: run main task and collect teardown tasks
            tasks_results = self.loop.run_until_complete(fut_main_task)
            yield tasks_results

            # stage 3: teardown
            self.loop.run_until_complete(asyncio.gather(*self.teardown, loop=self.loop))

        self.iterator = iterator()

    def __iter__(self):
        return self

    def __next__(self):
        return next(self.iterator)

    def cancel(self):
        self.components.get(CancelMainTask).set()


def run(*plugins, components=None, loop=None):
    """Start the asyncio process by boostrapping the root plugin.

    We have a three phase setup:

    1. run plugin hooks, to register arbitrary stuff and mainly gather a set of
    asyncio tasks for the second phase

    2. run all registered tasks together until complete

    3. run returned tasks for teardown
    """
    _, result = Staging(*plugins, components=components, loop=loop)
    return result


def resolve_plugin(plugin, function_name=PLUGIN_FUNCTION_NAME):
    plugin = resolve_dotted_name(plugin)
    if inspect.ismodule(plugin):
        # apply default name
        plugin = getattr(plugin, function_name)

    if not (inspect.iscoroutinefunction(plugin) or inspect.isasyncgenfunction(plugin)):
        raise ValueError(f"{plugin} must a coroutine or an async generator.")

    return plugin


def resolve_dotted_name(name):
    """Use pkg_resources style dotted name to resolve a name."""
    # skip resolving for module and coroutine
    if inspect.ismodule(name) or inspect.isroutine(name):
        return name

    # relative import
    if name.startswith("."):
        frame = inspect.currentframe()
        while frame.f_globals["__name__"].startswith(__package__):
            frame = frame.f_back
        caller_package = frame.f_globals["__package__"]
    else:
        caller_package = None

    part = ":"
    module_name, _, attr_name = name.partition(part)

    if part in attr_name:
        raise ValueError(f"Invalid name: {name}", name)

    resolved = importlib.import_module(module_name, caller_package)

    if attr_name:
        resolved = getattr(resolved, attr_name)

    return resolved


async def generate_async_result(fun_result):
    """Create an async generator out of any result."""
    if inspect.isasyncgen(fun_result):
        async for item in fun_result:
            yield item
    else:
        result = await fun_result

        # store tasks
        if isinstance(result, collections.abc.Iterable):
            for item in result:
                yield item
        elif result is not None:
            yield result


async def async_gen_to_list(task):
    sl.debug("Wrap task", task=task)
    if inspect.isasyncgen(task):
        lst = [item async for item in task]
        return lst
    return await task
