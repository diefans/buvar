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
