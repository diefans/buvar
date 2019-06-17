"""Very simple plugin architecture for asyncio."""
import asyncio
import collections
import collections.abc
import importlib
import inspect
import itertools
import sys

import structlog

from . import context
from .components import Components

PLUGIN_FUNCTION_NAME = 'plugin'
BUVAR_NAMESPACE = 'buvar'


class Bootstrap:

    """Maintain the plugin loading state."""

    def __init__(self, *, components=None, loop=None):
        self.loop = asyncio.get_event_loop() if loop is None else loop
        self.components = Components() if components is None else components

        # set task factory to serve our components context
        context.set_task_factory(self.components, loop=self.loop)

        # a collection of all tasks to run
        self.tasks = collections.OrderedDict()
        self.components.add(self.tasks, BUVAR_NAMESPACE, name='tasks')

        self.evt_plugins_loaded = asyncio.Event(loop=self.loop)
        self.components.add(
            self.evt_plugins_loaded, BUVAR_NAMESPACE, name='plugins_loaded')

        # schedule the main task, which waits until all plugins are loaded
        self.fut_main_task = asyncio.ensure_future(
            self._run_tasks(),
            loop=self.loop
        )
        self.components.add(
            self.fut_main_task, BUVAR_NAMESPACE, name='main_task')

    async def include(self, plugin):
        """Hook the plugin from another plugin.

        The plugin may return an awaitable, an iterable of awaitable or an
        asyncgenerator of awaitables.

        :param plugin: the plugin to load
        :type plugin: a callable which may have one argument, receiving the
        include callback
        """
        plugin = resolve_plugin(plugin)
        if plugin not in self.tasks:
            # mark plugin as loaded for recursive circular stuff
            self.tasks[plugin] = []
            # load plugin
            spec = inspect.getfullargspec(plugin)
            result = plugin(self.include) if len(spec.args) == 1 else plugin()
            callables = [fun async for fun in generate_async_result(result)]
            self.tasks[plugin].extend(callables)

    def load(self, plugin):
        try:
            self.loop.run_until_complete(self.include(plugin))
        except Exception as ex:     # noqa: E722
            # if a plugin raises an error, we cancel the scheduled main task
            import traceback
            logger = structlog.get_logger()
            logger.error('Error while loading plugins',
                         exception=ex, traceback=traceback.format_exc())
            # cancel prepared main task
            self.fut_main_task.cancel()
            self.loop.run_until_complete(self.fut_main_task)
            raise

    def run(self):
        try:
            return self.fut_main_task
        finally:
            self.evt_plugins_loaded.set()

    async def _run_tasks(self):
        # we wait for plugin loading completed
        try:
            await self.evt_plugins_loaded.wait()
        except asyncio.CancelledError:
            # we were in plugin loading stage
            # so we just return and finish
            return

        # run all tasks together
        current_tasks = self.tasks.values()
        result_list = await asyncio.gather(
            *expand_async_generator(
                itertools.chain(*current_tasks)
            ),
            return_exceptions=True,
            loop=self.loop
        )
        # flatten tasks
        teardown_tasks = list(flatten_tasks(result_list))
        return teardown_tasks


def staging(*plugins, components=None, loop=None):
    """Generate all stages to run an application.

    >>> components = Components()
    >>> loop = asyncio.get_event_loop()
    >>> async def plugin(load):
    ...     async def some_task():
    ...         async def teardown():
    ...             pass
    ...         yield teardown()
    ...     yield some_task()


    >>> stages = staging(components=components, loop=loop)
    >>> load = next(stages)
    >>> load(plugin)

    >>> # finish bootstrap and run main task
    >>> main_task = next(stages)

    >>> # wait for main task to finish
    >>> teardown_tasks = next(stages)

    >>> # finsh
    >>> next(stages)


    >>> stages = staging(plugin, components=components, loop=loop)
    >>> for stage in stages:
    ...     pass
    """
    if components is None:
        components = Components()
    if loop is None:
        loop = asyncio.get_event_loop()

    evt_main_task_finished = asyncio.Event()
    components.add(
        evt_main_task_finished, BUVAR_NAMESPACE, name='main_task_finished')
    evt_teardown_finished = asyncio.Event()
    components.add(
        evt_teardown_finished, BUVAR_NAMESPACE, name='teardown_finished')

    # stage 1: bootstrap plugins
    bootstrap = Bootstrap(components=components, loop=loop)
    for plugin in plugins:
        bootstrap.load(plugin)
    yield bootstrap.load

    # stage 2: run main task
    fut_main_task = bootstrap.run()
    yield fut_main_task

    # finish bootstrap and start main task
    teardown_tasks = loop.run_until_complete(fut_main_task)
    evt_main_task_finished.set()
    yield teardown_tasks

    # stage 3: teardown
    loop.run_until_complete(asyncio.gather(*teardown_tasks, loop=loop))
    evt_teardown_finished.set()
    yield None


def run(*plugins, components=None, loop=None):
    """Start the asyncio process by boostrapping the root plugin.

    We have a three phase setup:

    1. run plugin hooks, to register arbitrary stuff and mainly gather a set of
    asyncio tasks in the second phase

    2. run all registered tasks together until complete

    3. run returned tasks for teardown
    """
    list(staging(*plugins, components=components, loop=loop))


def resolve_plugin(plugin, function_name=PLUGIN_FUNCTION_NAME):
    plugin = resolve_dotted_name(plugin)
    if inspect.ismodule(plugin):
        # apply default name
        plugin = getattr(plugin, function_name)

    if not (inspect.iscoroutinefunction(plugin)
            or inspect.isasyncgenfunction(plugin)):
        raise ValueError(
            f'{plugin} must a coroutine or an async generator.')

    return plugin


def resolve_dotted_name(name):
    """Use pkg_resources style dotted name to resolve a name."""
    # skip resolving for module and coroutine
    if inspect.ismodule(name)\
            or inspect.isroutine(name):
        return name

    # relative import
    if name.startswith('.'):
        target_name = name.split('.')
        frame = inspect.currentframe()
        while frame.f_globals['__name__'].startswith(__package__):
            frame = frame.f_back

        caller_name = frame.f_globals['__name__'].split('.')
        try:
            while not target_name[0]:
                caller_name.pop()
                target_name.pop(0)
            name = '.'.join(itertools.chain(caller_name, target_name))
        except IndexError:
            raise RuntimeError('Relative name gets out of parent packages!',
                               name)
    part = ':'
    module_name, _, attr_name = name.partition(part)
    if part in attr_name:
        raise ValueError(f'Invalid name: {name}', name)

    if module_name in sys.modules:
        resolved = sys.modules[module_name]
    else:
        spec = importlib.util.find_spec(module_name)
        if spec is None:
            raise ValueError(f'Invalid module: {module_name}', module_name)
        resolved = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(resolved)
        sys.modules[resolved.__name__] = resolved

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


async def async_gen_to_list(asyncgen):
    lst = [item async for item in asyncgen]
    return lst


def expand_async_generator(tasks):
    for task in tasks:
        if inspect.isasyncgen(task):
            yield async_gen_to_list(task)
        else:
            yield task


def flatten_tasks(result_list):
    for item in result_list:
        if inspect.isawaitable(item):
            yield item
        elif isinstance(item, collections.abc.Iterable):
            for sub_item in item:
                if inspect.isawaitable(sub_item):
                    yield sub_item
