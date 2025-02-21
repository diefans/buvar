import dataclasses as dc
import functools
import logging
import logging.config
import sys
import typing
from os import getpid

import structlog
from structlog.processors import JSONRenderer

from . import util


def stringify_dict_keys(obj):
    if isinstance(obj, list):
        obj = [stringify_dict_keys(item) for item in obj]
    elif isinstance(obj, tuple):
        obj = tuple(stringify_dict_keys(item) for item in obj)
    elif isinstance(obj, dict):
        obj = {str(key): stringify_dict_keys(value) for key, value in obj.items()}
    return obj


try:
    import orjson

    json_dumps_inner = functools.partial(
        orjson.dumps, option=orjson.OPT_NAIVE_UTC | orjson.OPT_NON_STR_KEYS
    )
    json_dumps = lambda *arg, **kwargs: json_dumps_inner(*arg, **kwargs).decode("utf-8")
except ImportError:
    import json

    json_dumps = json.dumps


LOGGING_LEVEL_NAMES = list(
    map(
        logging.getLevelName,
        sorted(
            (
                logging.NOTSET,
                logging.DEBUG,
                logging.INFO,
                logging.WARN,
                logging.ERROR,
                logging.CRITICAL,
            )
        ),
    )
)
DEFAULT_LOGGING_LEVEL = logging.getLevelName(logging.WARNING)
timestamper = structlog.processors.TimeStamper(fmt="ISO", utc=True)


@dc.dataclass
class LogConfig:
    tty: bool = sys.stdout.isatty()
    level: typing.Union[int, str] = logging.DEBUG
    user_config: typing.Optional[typing.Dict] = None
    capture_warnings: bool = True
    redirect_print: bool = False
    json_renderer: JSONRenderer = JSONRenderer(
        serializer=lambda obj, **kwargs: json_dumps(stringify_dict_keys(obj), **kwargs)
    )

    @property
    def processors(self):
        processors = [
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.PositionalArgumentsFormatter(),
            timestamper,
            add_os_pid,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ]
        return processors

    @property
    def pre_chain(self):
        pre_chain = [
            # Add the log level and a timestamp to the event_dict if the log entry
            # is not from structlog.
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.format_exc_info,
            timestamper,
            add_os_pid,
            # ExtractLogExtra(
            #     "spec",
            #     "url",
            #     "mimetype",
            #     "has_body",
            #     "swagger_yaml",
            #     "method",
            #     "path",
            #     "operation_id",
            #     "data",
            # ),
        ]
        return pre_chain

    def setup(self):
        level = (
            logging.getLevelName(self.level.upper())
            if isinstance(self.level, str)
            else self.level
        )

        renderer = structlog.dev.ConsoleRenderer() if self.tty else self.json_renderer
        config = {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "structured": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "processor": renderer,
                    "foreign_pre_chain": self.pre_chain,
                }
            },
            "handlers": {
                "default": {"class": "logging.StreamHandler", "formatter": "structured"}
            },
            "loggers": {
                "": {"handlers": ["default"], "level": level, "propagate": True}
            },
        }
        if self.user_config:
            util.merge_dict(self.user_config, dest=config)
        logging.config.dictConfig(config)

        logging.captureWarnings(self.capture_warnings)

        structlog.configure(
            processors=self.processors,
            context_class=structlog.threadlocal.wrap_dict(dict),
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )

        if self.redirect_print:
            # redirect stdio print
            print_log = structlog.get_logger("print")
            sys.stderr = StdioToLog(print_log)
            sys.stdout = StdioToLog(print_log)

        # log uncaught exceptions
        sys.excepthook = uncaught_exception


def setup_logging(**kwargs):
    log_config = LogConfig(**kwargs)
    log_config.setup()


class ExtractLogExtra:  # noqa: R0903
    """Extract log record attributes to structlog event_dict."""

    def __init__(self, *attrs):
        self.attrs = attrs

    def __call__(self, logger, method_name, event_dict):
        """
        Add the logger name to the event dict.
        """
        record = event_dict.get("_record")
        for attr_name in self.attrs:
            if hasattr(record, attr_name):
                attr = getattr(record, attr_name)
                event_dict[attr_name] = attr
        return event_dict


class StdioToLog:
    """Delegate sys.stdout to a logger."""

    def __init__(self, logger, log_level=logging.INFO):
        self.logger = logger
        self.log_level = log_level
        self.linebuf = ""

    def write(self, buf):  # noqa
        for line in buf.rstrip().splitlines():
            self.logger.log(self.log_level, line.rstrip())

    def flush(self):  # noqa
        pass


def add_os_pid(logger, method_name, event_dict):  # noqa
    event_dict["pid"] = getpid()
    return event_dict


def uncaught_exception(ex_type, ex_value, tb):  # noqa: C0103
    log_ = structlog.get_logger("sys.excepthook")
    log_.critical(event="uncaught exception", exc_info=(ex_type, ex_value, tb))
