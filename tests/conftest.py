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
        from buvar.di import resolve
        from buvar.components import py_components

        mocker.patch("buvar.di.nject", resolve.nject)
        mocker.patch("buvar.components.Components", py_components.Components)
        yield resolve.nject
    else:
        try:
            from buvar.di import c_resolve as resolve
            from buvar.components import c_components

            mocker.patch("buvar.di.nject", resolve.nject)
            mocker.patch("buvar.components.Components", c_components.Components)
            yield resolve.nject  # noqa: I1101
        except ImportError:
            pytest.skip(f"C extension {request.param} not available.")
            return
