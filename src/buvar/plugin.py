"""Very simple plugin architecture for asyncio."""
import asyncio
import collections
import collections.abc
import functools
import importlib
import inspect
import itertools
import sys

from . import context
from .components import Components

PLUGIN_FUNCTION_NAME = 'plug_me_in'
BUVAR_NAMESPACE = 'buvar'


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
        if inspect.isasyncgenfunction(plugin):
            plugin_tasks = [task async for task in plugin(_load)]
        else:
            plugin_tasks = await plugin(_load)

        # store tasks
        if isinstance(plugin_tasks, collections.abc.Iterable):
            tasks[plugin].extend(plugin_tasks)
        elif inspect.isawaitable(plugin_tasks):
            tasks[plugin].append(plugin_tasks)
        elif plugin_tasks is None:
            pass
        else:
            raise RuntimeError('Plugin must return a coroutine or an iterable'
                               ' of coroutines or an async generator of'
                               ' coroutines or None', plugin_tasks)


def bootstrap(plugin, *, components=None, loop=None):
    """Start the asyncio process by boostrapping the root plugin.

    We have a two phase setup:

    1. run plugin hooks, to register arbitrary stuff and mainly a set of
    asyncio tasks to gather in the second phase

    2. run all registered tasks together until complete
    """
    if loop is None:
        loop = asyncio.get_event_loop()

    # create components
    if components is None:
        components = Components()

    # set task factory to serve our components context
    loop.set_task_factory(
        functools.partial(
            context.task_factory,
            default=lambda _: components
        )
    )

    tasks = collections.OrderedDict()
    components.add(tasks, BUVAR_NAMESPACE, name='tasks')

    # prepare task gathering
    # to store its future in the context
    async def gather_tasks():
        results = await asyncio.gather(
            *itertools.chain(*tasks.values()),
            return_exceptions=True
        )
        return results

    fut_tasks = gather_tasks()
    components.add(fut_tasks, BUVAR_NAMESPACE, name='gathered_task')

    # load root plugin
    loop.run_until_complete(load(plugin, tasks))
    # run all collected tasks
    result = loop.run_until_complete(fut_tasks)
    return result


def resolve_plugin(plugin, function_name=PLUGIN_FUNCTION_NAME):
    plugin = resolve_dotted_name(plugin)
    if inspect.ismodule(plugin):
        # apply default name
        plugin = getattr(plugin, function_name)

    if not (inspect.iscoroutinefunction(plugin)
            or inspect.isasyncgenfunction(plugin)):
        raise ValueError(
            f'{plugin.__name__} must be an async function.')

    return plugin


def resolve_dotted_name(name):
    """Use pkg_resources style dotted name to resolve a name."""
    # skip resolving for module and coroutine
    if inspect.ismodule(name)\
            or inspect.iscoroutinefunction(name)\
            or inspect.isasyncgenfunction(name):
        return name

    part = ':'
    module_name, _, attr_name = name.partition(part)
    if part in attr_name:
        raise ValueError(f'Invalid name: {name}')

    if module_name in sys.modules:
        resolved = sys.modules[module_name]
    else:
        spec = importlib.util.find_spec(module_name)
        if spec is None:
            raise ValueError(f'Invalid module: {module_name}')
        resolved = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(resolved)
        sys.modules[resolved.__name__] = resolved

    if attr_name:
        resolved = getattr(resolved, attr_name)

    return resolved
