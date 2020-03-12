import pytest


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
