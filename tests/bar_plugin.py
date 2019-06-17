from buvar import context


async def bar():
    context.get('bar')


async def baz():
    pass


async def plugin_bar(include):
    context.add('bar', 'bar')
    yield bar()
    yield baz()
