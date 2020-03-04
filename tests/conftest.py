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
    else:
        try:
            from buvar.di import c_di as di_impl
            from buvar.components import c_components as cmps_impl
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
    mocker.patch("buvar.context.components", cmps_impl)
    # no way to do it with mocker
    patcher = mock.patch.object(di.Adapters, "__bases__", (dict, di_impl.AdaptersImpl))
    with patcher:
        patcher.is_local = True
        yield


@pytest.fixture
def adapters(implementation):
    from buvar import di

    adapters = di.Adapters()
    token = di.buvar_adapters.set(adapters)
    yield adapters
    di.buvar_adapters.reset(token)


@pytest.fixture(autouse=True)
def components(implementation):
    from buvar import context, Components

    components = Components()
    assert context.current_context()

    token = context.buvar_context.set(components)
    yield components
    context.buvar_context.reset(token)


@pytest.fixture
def context_task_factory(event_loop, components):
    from buvar import context

    return context.set_task_factory(loop=event_loop)


def pytest_configure(config):
    # register an additional marker
    config.addinivalue_line(
        "markers",
        f"{PLUGINS_MARK}(*plugins): mark test to run only on named environment",
    )


@pytest.fixture
def pushed_context(components):
    from buvar import context

    with context.child(*(components.stack if components else ())):
        yield


@pytest.fixture
@pytest.mark.usefixtures("pushed_context")
async def buvar_staged(request):
    import asyncio
    from buvar import plugin, context

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
        # prepare components
        context.add(plugin.Cancel())
        loader = context.add(plugin.Loader())
        teardown = context.add(plugin.Teardown())

        # stage 1: bootstrap plugins
        await loader(*plugins)

        # stage 2: run main task and collect teardown tasks
        fut_run = asyncio.create_task(plugin.run(loader.tasks))
        yield
        fut_run.cancel()
        await fut_run
    except Exception:
        raise

    finally:
        # stage 3: teardown
        await teardown.wait()
