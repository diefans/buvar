import pytest


@pytest.fixture(autouse=True, scope='session')
def my_fixture():
    from buvar import log
    log.setup_logging(tty=False)
    # setup_stuff
    yield
    # teardown_stuff
