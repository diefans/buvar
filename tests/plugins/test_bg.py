import pytest


@pytest.mark.asyncio
@pytest.mark.buvar_plugins("buvar.plugins.bg")
async def test_bg_error(buvar_stage, capsys):
    import json
    from buvar.plugins import bg
    from buvar import context, log

    log.setup_logging(tty=False)
    context.buvar_context.set(buvar_stage.context)

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
async def test_bg_semaphore(buvar_stage):
    import asyncio
    from buvar.plugins import bg
    from buvar import context

    context.buvar_context.set(buvar_stage.context)
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
