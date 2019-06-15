"""Very simple plugin architecture for asyncio."""
import asyncio
import collections
import collections.abc
import functools
import importlib
import inspect
import itertools
import sys

import structlog

from . import context
from .components import Components

PLUGIN_FUNCTION_NAME = 'plugin'
BUVAR_NAMESPACE = 'buvar'


class Stages:
    def __init__(self, plugin, *, components=None, loop=None):
        self.plugin = plugin
        self.components = Components() if components is None else components
        self.loop = asyncio.get_event_loop() if loop is None else loop

    def _bootstrap(self):
        # set task factory to serve our components context
        self.loop.set_task_factory(
            functools.partial(
                context.task_factory,
                default=lambda _: self.components
            )
        )

        # a collection of all tasks to run
        tasks = collections.OrderedDict()
        self.components.add(tasks, BUVAR_NAMESPACE, name='tasks')

        evt_plugins_loaded = asyncio.Event(loop=self.loop)
        self.components.add(
            evt_plugins_loaded, BUVAR_NAMESPACE, name='plugins_loaded')

        # schedule the main task, which waits until all plugin are loaded
        fut_main_task = asyncio.ensure_future(
            self._run_main_tasks(evt_plugins_loaded, tasks),
            loop=self.loop
        )
        self.components.add(
            fut_main_task, BUVAR_NAMESPACE, name='main_task')

        # load root plugin
        try:
            self.loop.run_until_complete(load(self.plugin, tasks))
        except Exception as ex:     # noqa: E722
            # if a plugin raises an error, we cancel the scheduled main task
            import traceback
            logger = structlog.get_logger()
            logger.error('Error while loading plugins',
                         exception=ex, traceback=traceback.format_exc())
            # cancel prepared main task
            fut_main_task.cancel()
            self.loop.run_until_complete(fut_main_task)
            raise
        else:
            yield fut_main_task
            evt_plugins_loaded.set()

    async def _run_main_tasks(self, evt_plugins_loaded, tasks):
        # we wait for plugin loading completed
        try:
            await evt_plugins_loaded.wait()
        except asyncio.CancelledError:
            # we were in plugin loading stage
            # so we just return and finish
            return

        # run all tasks together
        current_tasks = tasks.values()
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

    def generate(self):
        evt_main_task_finished = asyncio.Event()
        self.components.add(
            evt_main_task_finished, BUVAR_NAMESPACE, name='main_task_finished')
        evt_teardown_finished = asyncio.Event()
        self.components.add(
            evt_teardown_finished, BUVAR_NAMESPACE, name='teardown_finished')

        # stage 1: bootstrap plugins
        bootstrap = self._bootstrap()
        fut_main_task = next(bootstrap)     # noqa: R1708
        # main task still waiting
        yield fut_main_task

        # stage 2: run main task

        # finish bootstrap and start main task
        next(bootstrap, None)
        teardown_tasks = self.loop.run_until_complete(fut_main_task)
        evt_main_task_finished.set()
        yield teardown_tasks

        # stage 3: teardown
        self.loop.run_until_complete(asyncio.gather(*teardown_tasks, loop=self.loop))
        evt_teardown_finished.set()
        yield None


def run(plugin, *, components=None, loop=None):
    """Start the asyncio process by boostrapping the root plugin.

    We have a three phase setup:

    1. run plugin hooks, to register arbitrary stuff and mainly gather a set of
    asyncio tasks in the second phase

    2. run all registered tasks together until complete

    3. run returned tasks for teardown


    >>> components = Components()
    >>> loop = asyncio.get_event_loop()
    >>> async def plugin(load):
    ...     async def some_task():
    ...         async def teardown():
    ...             pass
    ...         yield teardown()
    ...     yield some_task()


    >>> stages = Stages(plugin, components=components, loop=loop).generate()
    >>> main_task = next(stages)
    >>> teardown_tasks = next(stages)
    >>> next(stages)
    >>> # just finish generator
    >>> next(stages, None)


    >>> stages = Stages(plugin, components=components, loop=loop).generate()
    >>> for stage in stages:
    ...     pass
    """
    stages = Stages(plugin, components=components, loop=loop).generate()
    list(stages)

    # for stage in stages:
    #     pass


async def load(plugin, tasks):
    """Hook the plugin.

    The plugin may return an awaitable, an iterable of awaitable or an
    asyncgenerator of awaitables.

    :param plugin: the plugin to load
    :param tasks: a dictionary to store all returned tasks
    """
    plugin = resolve_plugin(plugin)
    if plugin not in tasks:
        # mark plugin as loaded for recursive circular stuff
        tasks[plugin] = []
        # load plugin
        _load = functools.partial(load, tasks=tasks)
        result = plugin(_load)
        callables = [fun async for fun in generate_async_result(result)]
        tasks[plugin].extend(callables)


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
