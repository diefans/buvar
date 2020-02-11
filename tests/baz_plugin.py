from buvar import plugin


async def plugin(include: plugin.Loader):
    await include("....not.found")
