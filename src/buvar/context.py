"""Provide a component registry as contextvar."""
import asyncio
import contextlib
import contextvars
import functools

from . import components


buvar_context: contextvars.ContextVar = contextvars.ContextVar(__name__)

# we provide a global available context
buvar_context.set(components.Components())


class StackingTaskFactory:
    def __init__(self, *, parent_factory=None):
        self.parent_factory = parent_factory

    def __call__(self, loop, coro):
        with child():
            task = (
                self.parent_factory
                if self.parent_factory is not None
                else asyncio.tasks.Task
            )(loop=loop, coro=coro)
            return task

    @classmethod
    def set(cls, *, loop=None):
        if loop is None:
            loop = asyncio.get_event_loop()

        factory = cls(parent_factory=loop.get_task_factory())
        loop.set_task_factory(factory)
        return factory

    def reset(self, *, loop=None):
        if loop is None:
            loop = asyncio.get_event_loop()

        loop.set_task_factory(self.parent_factory)


set_task_factory = StackingTaskFactory.set


def current_context():
    return buvar_context.get()


def add(*args, **kwargs):
    context = current_context()
    return context.add(*args, **kwargs)


def get(*args, **kwargs):
    context = current_context()
    return context.get(*args, **kwargs)


def find(*args, **kwargs):
    context = current_context()
    return context.find(*args, **kwargs)


def push(*stack):
    parent_context = current_context()
    context = parent_context.push(*stack)
    token = buvar_context.set(context)
    return functools.partial(buvar_context.reset, token)


def pop():
    parent_context = current_context()
    context = parent_context.pop()
    token = buvar_context.set(context)
    return functools.partial(buvar_context.reset, token)


# https://www.python.org/dev/peps/pep-0568/
# https://stackoverflow.com/questions/53611690/how-do-i-write-consistent-stateful-context-managers
@contextlib.contextmanager
def child(*stack):
    reset = push(*stack)
    try:
        yield
    finally:
        reset()
