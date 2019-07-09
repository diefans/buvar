Búvár
=====

objective
---------

Basically I want something similar, what `Pyramid`_ provides, but for asyncio
and for a all kinds of services.

* Have a plugin system, which runs code not on import time, but on run time. So
  you can test and mock your code.

* Have a component registry to hold certain state of your application.

* Have a simple way to configure your application via OS environment.

* Have always a structlog.

.. _Pyramid: https://github.com/Pylons/pyramid


a use case
----------

`src/something/__main__.py`

.. code-block:: python

   """Main entry point to run the server."""
   import asyncio
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


   loop = asyncio.get_event_loop()
   user_config = toml.load(
       os.environ.get("USER_CONFIG", os.path.dirname(__file__) + "/user_config.toml")
   )

   cmps = components.Components()
   source = cmps.add(config.ConfigSource(user_config, env_prefix="APP"))
   general_config = cmps.add(source.load(GeneralConfig))

   log.setup_logging(sys.stdout.isatty(), general_config.log_level)

   sl = structlog.get_logger()
   sl.info("Starting process", pid=os.getpid())
   sl.debug("Config used", **source)

   plugin.run(*general_config.plugins, components=cmps, loop=loop)


`src/something/user_config.toml`

.. code-block:: toml

   log_level = "DEBUG"
   plugins = ['app']

   [aiohttp]
   host = "127.0.0.1"
   port = 5000



`src/something/__init__.py`

.. code-block:: python

   import aiohttp.web
   import structlog

   from buvar import context

   log = structlog.get_logger()
   routes = aiohttp.web.RouteTableDef()


   @routes.get("/")
   async def index(request):
       return aiohttp.web.json_response({"hello": "world"})


   async def plugin(include):
       await include(".server")
       app = context.get(aiohttp.web.Application)
       app.add_routes(routes)

`src/something/server.py`

.. code-block:: python

   """Create a aiohttp server task and provide the application via context."""
   import aiohttp.web
   import attr
   import structlog

   from buvar import config, context

   sl = structlog.get_logger()


   @attr.s(auto_attribs=True)
   class AioHttpConfig:
       host: str = "0.0.0.0"
       port: int = 8080


   class AccessLogger(aiohttp.abc.AbstractAccessLogger):  # noqa: R0903
       def log(self, request, response, time):  # noqa: R0201
           sl.info(
               "Access",
               remote=request.remote,
               method=request.method,
               path=request.path,
               time=time,
               status=response.status,
           )


   async def plugin():
       config_source = context.get(config.ConfigSource)
       aiohttp_config = config_source.load(AioHttpConfig, "aiohttp")
       aiohttp_app = context.add(
           aiohttp.web.Application(middlewares=[aiohttp.web.normalize_path_middleware()])
       )

       sl.info("Running web server", host=aiohttp_config.host, port=aiohttp_config.port)
       # return server task
       yield aiohttp.web._run_app(  # noqa: W0212
           aiohttp_app, host=aiohttp_config.host, port=aiohttp_config.port, print=None
       )




.. code-block:: bash

   cd src
   APP_AIOHTTP_HOST=0.0.0.0 APP_AIOHTTP_PORT=8080 python -m something

.. code-block::

   2019-07-09T20:52:40.979551Z [info     ] Starting process               [__main__] pid=13158
   2019-07-09T20:52:40.979753Z [debug    ] Config used                    [__main__] aiohttp={'host': '127.0.0.1', 'port': 5000} log_level=DEBUG pid=13158 plugins=['app']
   2019-07-09T20:52:40.980269Z [debug    ] Using selector: EpollSelector  [asyncio] pid=13158
   2019-07-09T20:52:40.981489Z [info     ] Running web server             [app.server] host=0.0.0.0 pid=13158 port=8080
