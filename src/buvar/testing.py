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
async def buvar_stage_loop(): ...


@pytest.fixture
def buvar_stage(buvar_context, buvar_stage_loop):
    # INFO: we need to depend on an async fixture, since Stage attaches to asyncio.get_event_loop()
    # pytest-asyncio would otherwise use another loop for the specific test
    from buvar import plugin

    # Restore ability to cancel whole test suite
    class SignalsAllowingInterrupt(plugin.Signals):
        def handle_int(self):
            super().handle_int()
            raise KeyboardInterrupt

    stage = plugin.Stage(components=buvar_context, signals=SignalsAllowingInterrupt)
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
    """The shared context while plugins are prepared.

    The global buvar context is installed during fixture setup so that the
    contextvars context captured by pytest-asyncio when it runs the test
    coroutine already contains the plugin context.
    """
    from buvar import context as buvar_context_module

    token = buvar_context_module.buvar_context.set(buvar_stage.context)
    try:
        yield buvar_stage.context
    finally:
        buvar_context_module.buvar_context.reset(token)


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


@pytest.fixture
def reset_buvar_context():
    from buvar import components, context

    token = context.buvar_context.set(components.Components())
    yield
    context.buvar_context.reset(token)


@pytest.fixture(autouse=True)
def reset_config_sections(mocker):
    from buvar import config

    old = config.Config.__buvar_config_sections__
    config.Config.__buvar_config_sections__ = {}
    yield
    config.Config.__buvar_config_sections__ = old
