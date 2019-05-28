from buvar import context


async def bar():
    context.get('bar')


async def baz():
    pass


async def plugin_bar(load):
    context.add('bar', 'bar')
    yield bar()
    yield baz()
