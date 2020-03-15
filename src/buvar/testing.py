import pytest

PLUGINS_MARK = "buvar_plugins"


def pytest_configure(config):
    # register an additional marker
    config.addinivalue_line(
        "markers",
        f"{PLUGINS_MARK}(*plugins): mark test to run only on named environment",
    )


def pytest_runtest_setup(item):
    if PLUGINS_MARK in item.keywords and buvar_tasks.__name__ not in item.fixturenames:
        item.fixturenames.extend((buvar_stage.__name__, buvar_tasks.__name__))


@pytest.fixture
def buvar_stage(event_loop):
    from buvar import plugin

    stage = plugin.Stage(loop=event_loop)
    return stage


@pytest.fixture
def buvar_tasks(request, buvar_stage):
    # get plugins from mark
    plugins = next(
        (
            mark.args
            for mark in request.node.iter_markers()
            if mark.name == PLUGINS_MARK
        ),
        (),
    )

    try:
        # stage 1: bootstrap plugins
        if plugins:
            buvar_stage.load(*plugins)

        # stage 2: tasks
        yield buvar_stage.loader.tasks
    except Exception:
        raise

    finally:
        # stage 3: teardown
        buvar_stage.run_teardown()


@pytest.hookimpl(hookwrapper=True)
def pytest_pyfunc_call(pyfuncitem):
    if PLUGINS_MARK in pyfuncitem.keywords:
        stage = pyfuncitem.funcargs[buvar_stage.__name__]
        pyfuncitem.obj = wrap_in_buvar_stage_context(stage.context, pyfuncitem.obj)

    yield


def wrap_in_buvar_stage_context(context, func):
    """Enable test function to run in plugin context."""
    import functools
    import contextvars

    from buvar.context import buvar_context

    ctx = contextvars.copy_context()

    @functools.wraps(func)
    def inner(**kwargs):
        def wrapper():
            buvar_context.set(context)
            return func(**kwargs)

        return ctx.run(wrapper)

    return inner
