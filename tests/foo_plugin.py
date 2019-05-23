from buvar import context


async def foo():
    return context.find(str)


async def plug_me_in(load):
    await load('tests.bar_plugin')
    context.add('foo', name='foo')

    return foo()
