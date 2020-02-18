from buvar import plugin


async def prepare(include: plugin.Loader):
    await include("....not.found")
