from buvar import context


async def foo():
    ctx = context.find(str)
    context.add(ctx, 'foo_plugin')


async def plugin(load):
    await load('.bar_plugin:plugin_bar')
    context.add('foo', name='foo')

    return foo()