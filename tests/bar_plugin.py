from buvar import context


async def bar():
    return context.get('bar')


async def baz():
    return 'baz'


async def plug_me_in(load):
    context.add('bar', 'bar')
    yield bar()
    yield baz()
