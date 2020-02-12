Búvár
=====

This is heavily inspired by `Pyramid`_ and my daily needs to fastly create and
maintain microservice like applications.


a plugin mechanic
-----------------


- plugin may depend on other plugins

- plugins yield tasks to run

- a registry serves as a store for application components created by plugins

- a dependency injection creates intermediate components

- a config source is mapped to plugin specific needs

- structlog boilerplate for json/tty logging


You bootstrap like following:

.. code-block:: python

    from buvar import plugin

    plugin.run("some.module.with.plugin.function")


.. code-block:: python

   # some.module.with.plugin.function
   from buvar import context, plugin

   class Foo:
       ...


   async def task():
       asyncio.sleep(1)


   async def server():
       my_component = context.get(Foo)
       await asyncio.Future()


   # you may omit include in arguments
   async def plugin(load: plugin.Loader):
       await load('.another.plugin')

       # create some long lasting components
       my_component = context.add(Foo())

       # you may run simple tasks
       yield task()

       # you may run server tasks
       yield server()


a components and dependency injection solution
----------------------------------------------

Dependency injection relies on registered adapters, which may be a function, a
method, a class, a classmethod or a generic classmthod.

Dependencies are looked up in components or may be provided via, arguments.


.. code-block:: python

   from buvar import di

   class Bar:
       pass

   class Foo:
       def __init__(self, bar: Bar = None):
           self.bar = bar

       @classmethod
       async def adapt(cls, baz: str) -> Foo:
           return Foo()

   async def adapt(bar: Bar) -> Foo
       foo = Foo(bar)
       return foo


   async def task():
       foo = await di.nject(Foo, baz="baz")
       assert foo.bar is None

       bar = Bar()
       foo = await di.nject(Foo, bar=bar)
       assert foo.bar is bar

   async def plugin():
       di.register(Foo.adapt)
       di.register(adapt)



a config source
---------------

`buvar.config.ConfigSource` is just a `dict`, which merges
arbitrary dicts into one. It serves a the single source of truth for
application variability.

You can load a section of config values into your custom `attrs`_ class instance. ConfigSource will override values by environment variables if present.


`config.toml`

.. code-block:: toml

   log_level = "DEBUG"
   show_warnings = "yes"

   [foobar]
   some = "value"


.. code-block:: bash

   export APP_FOOBAR_SOME=thing


.. code-block:: python

   import attr
   import toml

   from buvar import config

   @attr.s(auto_attribs=True)
   class GeneralConfig:
       log_level: str = "INFO"
       show_warnings: bool = config.bool_var(False)


   @attr.s(auto_attribs=True)
   class FoobarConfig:
      some: str


   source = config.ConfigSource(toml.load('config.toml'), env_prefix="APP")

   general_config = source.load(GeneralConfig)
   assert general_config == GeneralConfig(log_level="DEBUG", show_warnings=True)

   foobar_config = source.load(FoobarConfig, 'foobar')
   assert foobar_config.some == "thing"


There is a shortcut to the above approach provided by
`buvar.config.Config`, which requires to be subclassed from it with a
distinct `section` attribute. If one adds a `buvar.config.ConfigSource`
component, he will receive the mapped config in one call.

.. code-block:: python

   from buvar import config
   from buvar.plugin import Loader


   @attr.s(auto_attribs=True)
   class GeneralConfig(config.Config):
       log_level: str = "INFO"
       show_warnings: bool = config.bool_var(False)


   @attr.s(auto_attribs=True)
   class FoobarConfig(config.Config, section="foobar"):
       some: str


   async def plugin(load: Loader):
       # this would by typically placed in the main entry point
       source = context.add(config.ConfigSource(toml.load('config.toml'), env_prefix="APP"))

       # to provide the adapter to di, which could also be done inthe main entry point
       await load(config)
       foobar_config = await di.nject(FoobarConfig)


a structlog
-----------

Just `structlog`_ boilerplate.

.. code-block:: python

   import sys

   from buvar import log

   log.setup_logging(sys.stdout.isatty(), general_config.log_level)


.. _Pyramid: https://github.com/Pylons/pyramid
.. _structlog: https://www.structlog.org/en/stable/
.. _attrs: https://www.attrs.org/en/stable/
