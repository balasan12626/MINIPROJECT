import asyncio

from backend.simulation.engine import SimulationEngine


def test_stop_task_waits_for_cancel_handler():
    """Re-run bug: the old loop's CancelledError handler wrote status="paused"
    after the new run had set "running", so the new run stopped at ~tick 2."""

    async def scenario():
        eng = SimulationEngine()

        async def old_loop():
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                eng.status = "paused"
                raise

        eng.status = "running"
        eng.task = asyncio.create_task(old_loop())
        await asyncio.sleep(0)
        await eng._stop_task()
        eng.status = "running"  # what start() does next
        await asyncio.sleep(0.01)
        return eng.status, eng.task

    status, task = asyncio.run(scenario())
    assert status == "running"
    assert task is None
