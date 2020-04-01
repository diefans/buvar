import pytest


@pytest.mark.parametrize(
    "obj, result",
    [
        (None, None),
        (1, 1),
        (1.2, 1.2),
        (True, True),
        ((1, False, {1: 2}), (1, False, {"1": 2})),
        ({1: 1, 1.2: 1.2, None: None}, {"1": 1, "1.2": 1.2, "None": None}),
        ({1: {2: 3}}, {"1": {"2": 3}}),
    ],
)
def test_stringify_dict_keys(obj, result):
    from buvar.log import stringify_dict_keys

    stringified = stringify_dict_keys(obj)
    assert stringified == result


def test_simple_structlog_json(capsys, mocker):
    from buvar import log
    import logging
    import structlog
    import json

    mocker.patch(
        "structlog.processors._make_stamper", return_value=lambda event_dict: event_dict
    )
    mocker.patch(
        "buvar.log.add_os_pid",
        side_effect=lambda logger, method_name, event_dict: event_dict,
    )

    log.setup_logging(tty=False)

    sl = structlog.get_logger("foobar")
    logging.debug("foobar: %s", 123)
    sl.info("message", foo={123: "bar"})
    captured = capsys.readouterr()
    msgs = list(map(json.loads, captured.err.strip().split("\n")))
    assert msgs == [
        {"event": "foobar: 123", "level": "debug", "logger": "root"},
        {
            "event": "message",
            "foo": {"123": "bar"},
            "level": "info",
            "logger": "foobar",
        },
    ]
