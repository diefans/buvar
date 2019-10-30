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
import importlib
import inspect
import itertools

import structlog

from . import context
from .components import Components

PLUGIN_FUNCTION_NAME = "plugin"


sl = structlog.get_logger()


class CancelStaging(asyncio.Event):
    pass


class Bootstrap:
    """Maintain the plugin loading state."""

    def __init__(self, *, loop=None):
        self.plugin_tasks = collections.OrderedDict()
        self.loop = loop or asyncio.get_event_loop()

    async def include(self, plugin):
        """Hook the plugin from another plugin.

        The plugin may return an awaitable, an iterable of awaitable or an
        asyncgenerator of awaitables.

        :param plugin: the plugin to load
        :type plugin: a callable which may have one argument, receiving the
        include callback
        """
        plugin = resolve_plugin(plugin)
        if plugin not in self.plugin_tasks:
            # mark plugin as loaded for recursive circular stuff
            self.plugin_tasks[plugin] = []
            # load plugin
            spec = inspect.getfullargspec(plugin)
            result = plugin(self.include) if len(spec.args) == 1 else plugin()
            callables = [fun async for fun in generate_async_result(result)]
            self.plugin_tasks[plugin].extend(callables)

    def load(self, plugin):
        """Load a plugin."""
        self.loop.run_until_complete(self.include(plugin))

    def tasks(self):
        return iter(itertools.chain(*self.plugin_tasks.values()))


class Teardown:
    """A collection of teardown tasks."""

    def __init__(self):
        self.tasks = []

    def add(self, task):
        self.tasks.append(task)

    def __iter__(self):
        """We teardown in the reverse order of registration."""
        return reversed(self.tasks)


class Staging(Bootstrap):
    """Generate all stages to run an application."""

    def __init__(self, *plugins, components=None, loop=None):
        super().__init__(loop=loop)
        self.components = components if components is not None else Components()

        # set task factory to serve our components context
        self.task_factory = context.set_task_factory(self.components, loop=self.loop)

        # provide cancel event
        self.evt_cancel_main_task = self.components.add(CancelStaging(loop=self.loop))

        # provide a collection for teardown tasks
        self.teardown = self.components.add(Teardown())

        def iterator():
            try:
                # stage 1: bootstrap plugins
                for plugin in plugins:
                    self.load(plugin)
                # we yield load to additionally load arbitrary stuff, after standard
                # plugin loading
                yield self.load

                # elevate the context
                self.task_factory.enable_stacking()

                # stage 2: run main task and collect teardown tasks
                results = self.loop.run_until_complete(self.run())
                yield results
            finally:
                # stage 3: teardown
                self.loop.run_until_complete(
                    asyncio.gather(*self.teardown, loop=self.loop)
                )

        self.iterator = iterator()

    async def run(self):
        fut_tasks = asyncio.ensure_future(asyncio.gather(*self.tasks()))
        # stop staging if we finish in any way
        fut_tasks.add_done_callback(lambda fut_tasks: self.evt_cancel_main_task.set())

        # wait for exit
        await self.evt_cancel_main_task.wait()

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

    def __iter__(self):
        return self

    def __next__(self):
        return next(self.iterator)


def run(*plugins, components=None, loop=None):
    """Start the asyncio process by boostrapping the root plugin.

    We have a three phase setup:

    1. run plugin hooks, to register arbitrary stuff and mainly gather a set of
    asyncio tasks for the second phase

    2. run all registered tasks together until complete
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
