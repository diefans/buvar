"""A simple background job manager."""
import asyncio
import sys

import structlog

from buvar import context, plugin, util

sl = structlog.get_logger()


class Jobs(set):
    def add(self, job, *, sync=None):
        frame = sys._getframe(1)
        module_name = frame.f_globals["__name__"]

        sl.info("Add background job", job=job, module=module_name)
        fut_job = asyncio.ensure_future(self.job(sync, job))

        super().add(fut_job)
        fut_job.add_done_callback(self.remove)

        return fut_job

    @util.methdispatch
    def job(self, sync, job):
        return job

    @job.register
    def semaphore_job(self, semaphore: asyncio.Semaphore, job):
        async def semaphore_job():
            async with semaphore:
                return await job

        return semaphore_job()

    def remove(self, fut):
        try:
            _ = fut.result()
        except Exception as ex:
            sl.error("Background job failed", exc_info=ex)
        finally:
            super().remove(fut)

    def cancel(self):
        for job in self:
            job.cancel()

    def __await__(self):
        return asyncio.gather(*self, return_exceptions=True).__await__()

    async def shutdown(self):
        self.cancel()
        await self


async def prepare(teardown: plugin.Teardown):
    jobs = context.add(Jobs())
    teardown.add(jobs.shutdown())
