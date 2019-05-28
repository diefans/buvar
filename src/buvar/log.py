import logging
import logging.config
import os
import sys

import orjson
import structlog

LOGGING_LEVEL_NAMES = list(map(logging.getLevelName, sorted((
    logging.NOTSET, logging.DEBUG, logging.INFO,
    logging.WARN, logging.ERROR, logging.CRITICAL,
))))
DEFAULT_LOGGING_LEVEL = logging.getLevelName(logging.WARNING)
PID = os.getpid()


class ExtractLogExtra:      # noqa: R0903

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
        self.linebuf = ''

    def write(self, buf):   # noqa
        for line in buf.rstrip().splitlines():
            self.logger.log(self.log_level, line.rstrip())

    def flush(self):        # noqa
        pass


def add_os_pid(logger, method_name, event_dict):        # noqa
    """Add the logger name to the event dict."""
    event_dict["pid"] = PID
    return event_dict


class OrJsonRenderer:
    def __init__(self, option=orjson.OPT_NAIVE_UTC):    # noqa: I1101
        self.option = option

    def __call__(self, logger, name, event_dict):
        return orjson.dumps(event_dict,                 # noqa: I1101
                            default=lambda obj: str(repr(obj)),
                            option=self.option)


def setup_logging(tty=True, level=logging.DEBUG, capture_warnings=True,
                  redirect_print=False):
    """Set up structured logging for logstash.

    :param tty: if True renders colored logs
    :param level: the log level to be applied
    :param capture_warnings: redirect warnings to the logger
    :param redirect_print: use the logger to redirect printed messages
    """
    # normalize level
    if isinstance(level, str):
        level = logging.getLevelName(level.upper())

    renderer = (structlog.dev.ConsoleRenderer()
                if tty else OrJsonRenderer()
                )
    timestamper = structlog.processors.TimeStamper(fmt="ISO", utc=True)
    pre_chain = [
        # Add the log level and a timestamp to the event_dict if the log entry
        # is not from structlog.
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        add_os_pid,
        structlog.processors.format_exc_info,
        ExtractLogExtra('spec', 'url', 'mimetype', 'has_body', 'swagger_yaml',
                        'method', 'path', 'operation_id', 'data'),
        timestamper,
    ]

    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "plain": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": renderer,
                "foreign_pre_chain": pre_chain,
            },
            "colored": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": renderer,
                "foreign_pre_chain": pre_chain,
            },
        },
        "handlers": {
            "default": {
                # "level": "DEBUG",
                "class": "logging.StreamHandler",
                "formatter": "colored",
            },
            # "file": {
            #     # "level": "DEBUG",
            #     "class": "logging.handlers.WatchedFileHandler",
            #     "filename": "test.log",
            #     "formatter": "plain",
            # },
        },
        "loggers": {
            "": {
                "handlers": ["default"],
                "level": level,
                "propagate": True,
            },
        }
    })
    logging.captureWarnings(capture_warnings)
    processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        add_os_pid,
        structlog.stdlib.PositionalArgumentsFormatter(),
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ]

    structlog.configure(
        processors=processors,
        context_class=structlog.threadlocal.wrap_dict(dict),
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    if redirect_print:
        # redirect stdio print
        print_log = structlog.get_logger('print')
        sys.stderr = StdioToLog(print_log)
        sys.stdout = StdioToLog(print_log)

    # log uncaught exceptions
    sys.excepthook = uncaught_exception


def uncaught_exception(ex_type, ex_value, tb):  # noqa: C0103
    log_ = structlog.get_logger('sys.excepthook')
    log_.critical(event='uncaught exception', exc_info=(ex_type, ex_value, tb))
