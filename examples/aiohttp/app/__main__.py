"""Main entry point to run the server."""
import os
import sys
import typing

import attr
import toml
import structlog

from buvar import components, config, log, plugin


@attr.s(auto_attribs=True)
class GeneralConfig:
    """Simple config."""

    log_level: str = "INFO"
    plugins: typing.Set[str] = set()


# get config from file
user_config = toml.load(
    os.environ.get("USER_CONFIG", os.path.dirname(__file__) + "/user_config.toml")
)

# your components registry
cmps = components.Components()

# make config values overwritable by environment vars
source = cmps.add(config.ConfigSource(user_config, env_prefix="APP"))
general_config = cmps.add(source.load(GeneralConfig))

# setup structlog
log.setup_logging(tty=sys.stdout.isatty(), level=general_config.log_level)

sl = structlog.get_logger()
sl.info("Starting process", pid=os.getpid())
sl.debug("Config used", **source)

plugin.stage(config, *general_config.plugins, components=cmps)
