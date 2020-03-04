"""Very simple plugin architecture for asyncio.

    >>> loop = asyncio.get_event_loop()
    >>> state = {}
    >>> async def prepare(load: Loader):
    ...     async def some_task():
    ...         state['task'] = True
    ...     yield some_task()


    >>> stages = evolve()
    >>> load = next(stages)
    >>> load(prepare)

    >>> # wait for main task to finish
    >>> tasks_results = next(stages)

    >>> # finsh
    >>> next(stages, None)

    >>> assert state == {'task': True}


    >>> state = {}
    >>> for stage in evolve(prepare):
    ...     pass

    >>> assert state == {'task': True}
"""
import asyncio
import collections.abc
import importlib
import inspect
import itertools
import typing

import structlog

from . import context

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


class Loader(dict):
    """Load plugins and collect tasks."""

    @property
    def tasks(self):
        return iter(itertools.chain(*self.values()))

    async def __call__(self, *plugins):
        """Hook the plugin from another plugin.

        The plugin may return an awaitable, an iterable of awaitable or an
        asyncgenerator of awaitables.

        :param plugins: the plugin to load
        :type plugins: list of callables which may have one argument
        """
        for plugin in plugins:
            plugin = resolve_plugin_func(plugin)
            if plugin not in self:
                # mark plugin as loaded for recursive circular stuff
                self[plugin] = []
                # load plugin
                args = collect_plugin_args(plugin)
                try:
                    result = plugin(**args)
                except TypeError as ex:
                    raise TypeError(*ex.args, plugin.__module__, plugin.__name__)
                callables = [fun async for fun in generate_async_result(result)]
                self[plugin].extend(callables)


def evolve(*plugins, components=None, loop=None):
    """Generate all stages to run an application."""
    loop = loop or asyncio.get_event_loop()
    with context.child(*(components.stack if components else ())):
        # provide basic components
        cancel = context.add(Cancel(loop=loop))
        teardown = context.add(Teardown())
        loader = context.add(Loader())

        try:
            # stage 1: bootstrap plugins
            loop.run_until_complete(loader(*plugins))
            # we yield a synchronous loader, to externally continue loading
            yield lambda *plugins: loop.run_until_complete(loader(*plugins))

            # stage 2: run main task and collect teardown tasks
            results = loop.run_until_complete(
                run(tasks=loader.tasks, evt_cancel=cancel)
            )
            yield results
        finally:
            # stage 3: teardown
            loop.run_until_complete(teardown.wait())


async def run(tasks, *, evt_cancel=None):
    if evt_cancel is None:
        evt_cancel = context.add(Cancel())

    fut_tasks = asyncio.ensure_future(asyncio.gather(*tasks))
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


def stage(*plugins, components=None, loop=None):
    """Start the asyncio process by boostrapping the root plugin.

    We have a three phase setup:

    1. run plugin hooks, to register arbitrary stuff and mainly gather a set of
    asyncio tasks for the second phase

    2. run all registered tasks together until complete
    """

    if loop is None:
        loop = asyncio.get_event_loop()

    _, result = evolve(*plugins, components=components, loop=loop)
    return result


def collect_plugin_args(plugin):
    hints = typing.get_type_hints(plugin)
    args = {name: context.get(cls) for name, cls in hints.items()}
    return args


def resolve_plugin_func(plugin, function_name=PLUGIN_FUNCTION_NAME):
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
        if isinstance(result, collections.abc.Iterable):
            for item in result:
                yield item
        elif result is not None:
            yield result
