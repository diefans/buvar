"""Provide a component registry as task context."""
import asyncio
import sys

__all__ = ('get', 'add', 'find')

from .components import Components

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
        return Components()
    return parent_context


def task_factory(loop, coro, default=None):
    context = current_context(loop=loop)
    task = asyncio.tasks.Task(coro, loop=loop)

    if default is None:
        default = default_components_context

    setattr(task, 'context', default(context))
    return task


def current_context(loop=None):
    current_task = asyncio_current_task(loop=loop)
    context = getattr(current_task, 'context', None)
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
