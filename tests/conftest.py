import itertools

import pytest

PLUGINS_MARK = "buvar_plugins"


@pytest.fixture(autouse=True, scope="session")
def setup_logging():
    from buvar import log

    log.setup_logging(tty=False)
    # setup_stuff
    yield
    # teardown_stuff


@pytest.fixture(params=["cython", "python"], autouse=True)
def implementation(request, mocker):
    import mock

    # we run every test with cython and python
    from buvar import di

    if request.param == "python":
        from buvar.di import py_di as di_impl
        from buvar.components import py_components as cmps_impl

        # AdaptersImpl = py_di.AdaptersImpl
        # Components = py_components.Components
        # ComponentLookupError = py_components.ComponentLookupError
    else:
        try:
            from buvar.di import c_di as di_impl
            from buvar.components import c_components as cmps_impl

            # AdaptersImpl = c_di.AdaptersImpl
            # Components = c_components.Components
            # ComponentLookupError = c_components.ComponentLookupError
        except ImportError:
            pytest.skip(f"C extension {request.param} not available.")
            return

    mocker.patch("buvar.components.Components", cmps_impl.Components)
    mocker.patch(
        "buvar.components.ComponentLookupError", cmps_impl.ComponentLookupError
    )
    mocker.patch("buvar.Components", cmps_impl.Components)
    mocker.patch("buvar.ComponentLookupError", cmps_impl.ComponentLookupError)
    mocker.patch("buvar.di.missing", di_impl.missing)
    mocker.patch("buvar.di.ResolveError", di_impl.ResolveError)
    # no way to do it with mocker
    patcher = mock.patch.object(di.Adapters, "__bases__", (dict, di_impl.AdaptersImpl))
    with patcher:
        patcher.is_local = True
        yield


@pytest.fixture
def components():
    from buvar import Components

    return Components()


@pytest.fixture
def context_task_factory(event_loop, components):
    from buvar import context

    return context.set_task_factory(components, loop=event_loop)


def pytest_configure(config):
    # register an additional marker
    config.addinivalue_line(
        "markers",
        f"{PLUGINS_MARK}(*plugins): mark test to run only on named environment",
    )


@pytest.fixture
def staging(event_loop, components):
    from buvar import plugin

    staging = plugin.Staging(components=components, loop=event_loop)
    return staging


@pytest.fixture
async def buvar_staged(request, staging):
    import asyncio

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
        await staging.load_plugins(*plugins)

        # stage 2: run main task and collect teardown tasks
        fut_run = asyncio.ensure_future(staging.run())
        yield staging
        fut_run.cancel()
        await fut_run
    finally:
        # stage 3: teardown
        await staging.teardown.wait()
