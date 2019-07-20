"""Provide a component registry as task context."""
import asyncio
import contextlib
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


class TaskFactory:
    def __init__(self, *, root_context=None, default=None, parent_factory=None):
        self.default = default or self.default_components_context
        self.factory = (
            parent_factory if parent_factory is not None else asyncio.tasks.Task
        )
        self.root_context = (
            root_context if root_context is not None else components.Components()
        )

    def default_components_context(self, parent_context=None):
        """Context is always the same as the parents one."""
        if parent_context:
            return parent_context

        return self.root_context

    def __call__(self, loop, coro):
        task = self.factory(loop=loop, coro=coro)
        context = current_context(loop=loop)

        setattr(task, "context", self.default(context))
        return task


def set_task_factory(components, *, loop=None):  # noqa: W0621
    if loop is None:
        loop = asyncio.get_event_loop()

    task_factory = TaskFactory(
        root_context=components, parent_factory=loop.get_task_factory()
    )

    loop.set_task_factory(task_factory)


def current_context(loop=None):
    current_task = asyncio_current_task(loop=loop)
    context = getattr(current_task, "context", None)
    return context


def add(*args, **kwargs):
    context = current_context()
    return context.add(*args, **kwargs)


def get(*args, **kwargs):
    context = current_context()
    return context.get(*args, **kwargs)


def find(*args, **kwargs):
    context = current_context()
    return context.find(*args, **kwargs)


def push():
    current_task = asyncio_current_task()
    parent_context = getattr(current_task, "context", None)
    assert parent_context is not None, "There must be a context to push from."

    context = parent_context.push()
    setattr(current_task, "context", context)


def pop():
    current_task = asyncio_current_task()
    parent_context = getattr(current_task, "context", None)
    assert parent_context is not None, "There must be a context to pop from."

    context = parent_context.parents
    setattr(current_task, "context", context)


@contextlib.contextmanager
def child():
    push()
    yield
    pop()
