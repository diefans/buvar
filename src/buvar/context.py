"""Provide a component registry as contextvar."""

import asyncio
import contextlib
import contextvars
import functools
import sys

from . import components

buvar_context: contextvars.ContextVar[components.Components] = contextvars.ContextVar(
    __name__
)

# we provide a globally available context
buvar_context.set(components.Components())


class StackingTaskFactory:
    def __init__(self, *, parent_factory=None):
        self.parent_factory = parent_factory

    if sys.version_info < (3, 11):

        def __call__(self, loop, coro, context=None):
            component_context = current_context().push()
            token = buvar_context.set(component_context)
            # with child():
            task = (
                self.parent_factory
                if self.parent_factory is not None
                else asyncio.tasks.Task
            )(loop=loop, coro=coro)
            try:
                return task
            finally:
                buvar_context.reset(token)
    else:
        # INFO: Task() accepts context
        def __call__(self, loop, coro, context=None):
            component_context = current_context().push()
            token = buvar_context.set(component_context)
            # with child():
            task = (
                self.parent_factory
                if self.parent_factory is not None
                else asyncio.tasks.Task
            )(loop=loop, coro=coro, context=context)
            try:
                return task
            finally:
                buvar_context.reset(token)

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
    context = current_context().push(*stack)
    return context


def pop():
    context = current_context().pop()
    return context


# https://www.python.org/dev/peps/pep-0568/
# https://stackoverflow.com/questions/53611690/how-do-i-write-consistent-stateful-context-managers
@contextlib.contextmanager
def child(*stack):
    context = push(*stack)
    token = buvar_context.set(context)
    try:
        yield
    finally:
        buvar_context.reset(token)


def run(context: components.Components):
    """Run the decorated function within the provided context."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            def _child_context():
                buvar_context.set(context)
                return func(*args, **kwargs)

            ctx = contextvars.copy_context()
            return ctx.run(_child_context)

        return wrapper

    return decorator
