"""
Fixtures and markers for testing.

`buvar_plugins` mark

.. code-block::

    @pytest.mark.buvar_plugins("buvar.config")
"""

import pytest

PLUGINS_MARK = "buvar_plugins"


def pytest_configure(config):
    config.addinivalue_line(
        "markers", f"{PLUGINS_MARK}(*plugins): run the test in buvar plugin context"
    )


def pytest_runtest_setup(item):
    # use fixtures: buvar_plugin_context
    if (
        PLUGINS_MARK in item.keywords
        and buvar_plugin_context.__name__ not in item.fixturenames
    ):
        item.fixturenames.append(buvar_plugin_context.__name__)


@pytest.fixture
def buvar_config_source():
    from buvar import config

    config_source = config.ConfigSource()

    return config_source


@pytest.fixture
def buvar_context(buvar_config_source):
    from buvar import components

    context = components.Components()
    context.add(buvar_config_source)

    return context


@pytest.fixture
def buvar_stage(event_loop, buvar_context):
    from buvar import plugin

    stage = plugin.Stage(loop=event_loop, components=buvar_context)
    return stage


@pytest.fixture
def buvar_load(request, buvar_stage):
    """Load plugins marked via `pytest.mark.buvar_plugins`."""
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
        yield buvar_stage.loader
    except Exception:
        raise

    finally:
        # stage 3: teardown
        buvar_stage.run_teardown()


@pytest.fixture
def buvar_plugin_context(buvar_stage, buvar_load):
    """The shared context while plugins are prepared."""
    return buvar_stage.context


@pytest.hookimpl(hookwrapper=True, trylast=True)
def pytest_pyfunc_call(pyfuncitem):
    """Wrap marked tests in buvar plugin context."""
    if PLUGINS_MARK in pyfuncitem.keywords:
        plugin_context = pyfuncitem.funcargs[buvar_plugin_context.__name__]
        pyfuncitem.obj = wrap_in_buvar_plugin_context(plugin_context, pyfuncitem.obj)

    yield


def wrap_in_buvar_plugin_context(context, func):
    """Enable test function to run in plugin context."""
    import contextvars
    import functools

    from buvar.context import buvar_context

    ctx = contextvars.copy_context()

    @functools.wraps(func)
    def inner(**kwargs):
        def wrapper():
            buvar_context.set(context)
            return func(**kwargs)

        return ctx.run(wrapper)

    return inner


@pytest.fixture
def buvar_adapters_setup_contextvars():
    """Set and reset adapters.
    This fixture should be used, if you need to reset adapter registration for a test.
    """
    from buvar import di

    token = di.buvar_adapters.set(di.Adapters())
    yield
    di.buvar_adapters.reset(token)
