import asyncio

from buvar import context


async def plugin(load):
    import structlog

    logger = structlog.get_logger()

    fut = asyncio.Future()
    context.add(fut, name="server")
    evt_server_started = asyncio.Event()
    context.add(evt_server_started, name="server_started")

    async def server(fut):
        logger.info("Server started")
        evt_server_started.set()
        await fut
        logger.info("Server stopped")

    task = server(fut)
    return task
