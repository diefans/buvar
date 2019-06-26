"""Provide a component registry as task context."""
import asyncio
import functools
import sys

from . import components

__all__ = ("get", "add", "find")


PY37 = sys.version_info >= (3, 7)

if PY37:

    def asyncio_current_task(loop=None):
        """Return the current task or None."""
        try:
            return asyncio.current_task(loop)
        except RuntimeError:
            # simulate old behaviour
            return None


else:
    asyncio_current_task = asyncio.Task.current_task


def default_components_context(parent_context=None):
    if parent_context is None:
        return components.Components()
    return parent_context


def task_factory(loop, coro, default=None, parent_factory=None):
    context = current_context(loop=loop)

    factory = parent_factory if parent_factory is not None else asyncio.tasks.Task
    task = factory(loop=loop, coro=coro)

    if default is None:
        default = default_components_context

    setattr(task, "context", default(context))
    return task


def current_context(loop=None):
    current_task = asyncio_current_task(loop=loop)
    context = getattr(current_task, "context", None)
    return context


def add(*args, **kwargs):
    context = current_context()
    context.add(*args, **kwargs)


def get(*args, **kwargs):
    context = current_context()
    return context.get(*args, **kwargs)


def find(*args, **kwargs):
    context = current_context()
    return context.find(*args, **kwargs)


def push():
    context = current_context()
    return context.push()


def pop():
    context = current_context()
    return context.pop()


def set_task_factory(components, *, loop=None):  # noqa: W0621
    if loop is None:
        loop = asyncio.get_event_loop()

    loop.set_task_factory(
        functools.partial(
            task_factory,
            default=lambda _: components,
            parent_factory=loop.get_task_factory(),
        )
    )
