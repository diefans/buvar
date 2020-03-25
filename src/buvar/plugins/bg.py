"""A simple background job manager."""
import asyncio
import sys

import structlog

from buvar import Teardown, context

logger = structlog.get_logger()


class Jobs(set):
    def add(self, job):
        frame = sys._getframe(1)
        module_name = frame.f_globals["__name__"]

        logger.info("Add background job", job=job, module=module_name)
        return super().add(asyncio.ensure_future(job))

    def cancel(self):
        for job in self:
            job.cancel()

    def __await__(self):
        return asyncio.gather(*self).__await__()

    async def shutdown(self):
        self.cancel()
        await self


async def prepare():
    jobs = context.add(Jobs())
    context.get(Teardown).add(jobs.shutdown())
