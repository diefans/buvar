from buvar import context, plugin


async def bar():
    context.get("bar")


async def baz():
    await bam()
    pass


async def bam():
    pass


async def plugin_bar(include: plugin.Loader):
    context.add("bar", "bar")
    yield bar()
    yield baz()
