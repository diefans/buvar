Búvár
=====

a plugin mechanic
-----------------

I want to have a plugin mechanic similar to `Pyramid`_\'s aproach. It should
provide means to spawn arbitrary tasks to run, where every lifecycle stage
should be yielded to the developer control.

You bootstrap like following:

.. code-block:: python

    from buvar import plugin, components

    plugin.run("some.module.with.plugin.function")


.. code-block:: python

   # some.module.with.plugin.function
   from buvar import context


   # you may omit include in arguments
   async def plugin(include):
      await include('.another.plugin')

      # create some long lasting components
      my_component = context.add("some value")

      async def task():
         asyncio.sleep(1)

      async def server():
         await asyncio.Future()

      # you may run simple tasks
      yield task()

      # you may run server tasks
      yield server()


a components and dependency injection solution
----------------------------------------------

I want to have some utility to store some long lasting means of aid to my
business problem. I want a non-verbose lookup to those.

.. code-block:: python

   from buvar import di

   class Bar:
      pass

   class Foo:
      def __init__(self, bar: Bar = None):
         self.bar = bar

      @di.adapter_classmethod
      async def adapt(cls, baz: str) -> Foo:
         return Foo()

   @di.adapter
   async def adapt(bar: Bar) -> Foo
      foo = Foo(bar)
      return foo


   async def task():
      foo = await di.nject(Foo, baz="baz")
      assert foo.bar is None

      bar = Bar()
      foo = await di.nject(Foo, bar=bar)
      assert foo.bar is bar


a config source
---------------

I want to have a config source, which automatically applies environment
variables to the defaults.

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



a structlog
-----------

I want to have a nice and readable `structlog`_ in my terminal and a json log in
production.

.. code-block:: python

   import sys

   from buvar import log

   log.setup_logging(sys.stdout.isatty(), general_config.log_level)


.. _Pyramid: https://github.com/Pylons/pyramid
.. _structlog: https://www.structlog.org/en/stable/
