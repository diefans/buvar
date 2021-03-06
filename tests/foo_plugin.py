from buvar import context, plugin


async def foo():
    ctx = context.find(str)
    context.add(ctx, "foo_plugin")
    return ctx


async def prepare(include: plugin.Loader):
    await include(".bar_plugin:plugin_bar")
    context.add("foo", name="foo")

    return foo()
