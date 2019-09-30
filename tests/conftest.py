import pytest


@pytest.fixture(autouse=True, scope="session")
def setup_logging():
    from buvar import log

    log.setup_logging(tty=False)
    # setup_stuff
    yield
    # teardown_stuff


@pytest.fixture(params=["cython", "python"], autouse=True)
def implementation(request, mocker):
    # we run every test with cython and python
    if request.param == "python":
        from buvar.di import py_di
        from buvar.components import py_components

        Adapters = py_di.Adapters
        Components = py_components.Components
        ComponentLookupError = py_components.ComponentLookupError
    else:
        try:
            from buvar.di import c_di
            from buvar.components import c_components

            Adapters = c_di.Adapters
            Components = c_components.Components
            ComponentLookupError = c_components.ComponentLookupError
        except ImportError:
            pytest.skip(f"C extension {request.param} not available.")
            return
    mocker.patch("buvar.di.Adapters", Adapters)
    mocker.patch("buvar.components.Components", Components)
    mocker.patch("buvar.components.ComponentLookupError", ComponentLookupError)
    mocker.patch("buvar.Components", Components)
    mocker.patch("buvar.ComponentLookupError", ComponentLookupError)


@pytest.fixture
def cmps(event_loop, implementation):
    from buvar import context
    from buvar import Components

    cmps = Components()
    context.set_task_factory(cmps, loop=event_loop)
    return cmps
