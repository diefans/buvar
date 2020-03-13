import pytest

PLUGINS_MARK = "buvar_plugins"


def pytest_configure(config):
    # register an additional marker
    config.addinivalue_line(
        "markers",
        f"{PLUGINS_MARK}(*plugins): mark test to run only on named environment",
    )


# XXX FIXME
# https://github.com/pytest-dev/pytest/issues/6908
# def pytest_runtest_setup(item):
#     if (
#         PLUGINS_MARK
#         in set(mark.name for mark in item.iter_markers())
#         # and "buvar_tasks" not in item.fixturenames
#     ):
#         __import__("pdb").set_trace()  # XXX BREAKPOINT
#         item.add_marker(pytest.mark.usefixtures("buvar_tasks"), append=False)


# def pytest_collection_modifyitems(items):
#     for item in items:
#         if (
#             PLUGINS_MARK
#             in set(mark.name for mark in item.iter_markers())
#             # and "buvar_tasks" not in item.fixturenames
#         ):
#             item.add_marker(pytest.mark.usefixtures("buvar_tasks"), append=False)


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
        buvar_stage.load(*plugins)

        # stage 2: tasks
        yield buvar_stage.loader.tasks
    except Exception:
        raise

    finally:
        # stage 3: teardown
        buvar_stage.run_teardown()
