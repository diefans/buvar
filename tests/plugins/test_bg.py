import pytest


@pytest.mark.asyncio
@pytest.mark.buvar_plugins("buvar.plugins.bg")
async def test_bg_error(buvar_stage, capsys):
    # TODO XXX FIXME without buvar_stage, I get
    # --- Logging error ---
    # Traceback (most recent call last):
    #   File "/home/olli/.pyenv/versions/3.7.4/lib/python3.7/logging/__init__.py", line 1028, in emit
    #     stream.write(msg + self.terminator)
    # ValueError: I/O operation on closed file.
    import json
    from buvar.plugins import bg
    from buvar import context, log

    log.setup_logging(tty=False)

    async def make_error():
        raise Exception("foobar")

    jobs = context.get(bg.Jobs)

    jobs.add(make_error())

    await jobs
    captured = capsys.readouterr()
    msgs = list(map(json.loads, captured.err.strip().split("\n")))
    assert "Exception: foobar" in msgs[1]["exception"]


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
