import pytest


@pytest.mark.asyncio
@pytest.mark.buvar_plugins("buvar.plugins.bg")
async def test_bg_error(log_output, Anything):
    # TODO XXX FIXME without buvar_stage, I get
    # --- Logging error ---
    # Traceback (most recent call last):
    #   File "/home/olli/.pyenv/versions/3.7.4/lib/python3.7/logging/__init__.py", line 1028, in emit
    #     stream.write(msg + self.terminator)
    # ValueError: I/O operation on closed file.
    from buvar.plugins import bg
    from buvar import context

    async def make_error():
        raise Exception("foobar")

    jobs = context.get(bg.Jobs)

    jobs.add(make_error())

    await jobs
    assert {
        "event": "Background job failed",
        "exc_info": Anything,
        "log_level": "error",
    } in log_output.entries


@pytest.mark.asyncio
@pytest.mark.buvar_plugins("buvar.plugins.bg")
async def test_bg_semaphore():
    import asyncio
    from buvar.plugins import bg
    from buvar import context

    state = {"counter": 0, "sync": []}

    k = 3
    sem = asyncio.Semaphore(k)

    async def count():
        state["counter"] += 1
        await asyncio.sleep(0)
        state["sync"].append(state["counter"] % k)

    jobs = context.get(bg.Jobs)

    i = k * 10
    for _ in range(i):
        jobs.add(count(), sync=sem)

    await jobs
    assert state == {"counter": i, "sync": [0] * i}
