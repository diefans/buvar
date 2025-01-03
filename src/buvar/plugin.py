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

# XXX FIXME doctest sometime shows log messages
import asyncio
import collections.abc
import inspect
import itertools
import sys
import types
import typing as t
import signal

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
        # XXX TODO distinct between corotines, task, and normal functions
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


class Signals:
    handlers = (
        (signal.SIGINT, "handle_int"),
        (signal.SIGTERM, "handle_term"),
        (signal.SIGHUP, "handle_hup"),
        (signal.SIGQUIT, "handle_quit"),
        (signal.SIGABRT, "handle_abort"),
        (signal.SIGWINCH, "handle_winch"),
        (signal.SIGUSR1, "handle_usr1"),
        (signal.SIGUSR2, "handle_usr1"),
    )

    def __init__(self, stage):
        self.stage = stage
        self.add_signal_handlers()

    def add_signal_handlers(self):
        loop = self.stage.loop
        for signum, name in self.handlers:
            impl = getattr(self, name, None)
            if callable(impl):
                loop.add_signal_handler(signum, impl)

    # we really leave it open to the user how to handle signals
    # at least SIGINT makes sense
    def handle_int(self):
        self.stage.cancel.set()

    # def handle_term(self):
    #     ...

    # def handle_hup(self):
    #     ...

    # def handle_quit(self):
    #     ...

    # def handle_abort(self):
    #     ...

    # def handle_winch(self):
    #     ...

    # def handle_usr1(self):
    #     ...

    # def handle_usr2(self):
    #     ...


class Stage:
    """Stage manages the context stack while running each phase of the machinery.

    The stack typically has four layers:

    1. the default import time context

    2. the components context passed to the stage

    3. stage management context, e.g. Cancel, Teardown, Loader

    4. the shared plugin preparation context
    """

    def __init__(self, components=None, loop=None, signals: t.Type[Signals] = None):
        self.loop = loop or asyncio.get_event_loop()
        self.context = (
            context.current_context()
            .push(*(components.stack if components else ()))
            .push()
        )
        # provide basic components
        self.cancel = self.context.add(Cancel())
        self.teardown = self.context.add(Teardown())
        self.loader = self.context.add(Loader())
        self.signals = self.context.add((signals or Signals)(self))

        self.context = self.context.push()

    def load(self, *plugins):
        sl.info("Loading plugins")

        @context.run(self.context)
        def _load():
            self.loop.run_until_complete(self.loader(*plugins))

        _load()

    def run_tasks(self):
        sl.info("Running tasks", tasks=self.loader.tasks)

        @context.run(self.context)
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


def stage(*plugins, components=None, loop=None, signals: t.Type[Signals] = None):
    if loop is None:
        loop = asyncio.get_event_loop()

    stage = Stage(components=components, loop=loop, signals=signals)
    return stage.run(*plugins)


async def run(tasks, *, evt_cancel=None):
    if evt_cancel is None:
        evt_cancel = context.add(Cancel())

    # we automatically elevate context stack for tasks
    factory = context.set_task_factory()
    try:
        fut_tasks = asyncio.gather(*map(asyncio.create_task, tasks))

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
    finally:
        factory.reset()


def collect_plugin_args(plugin):
    hints = t.get_type_hints(plugin)
    args = {name: context.get(cls) for name, cls in hints.items()}
    return args


def resolve_plugin_func(
    plugin,
    *,
    function_name: str = PLUGIN_FUNCTION_NAME,
    caller: t.Union[types.FrameType, int] = 0,
) -> t.Callable:
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
