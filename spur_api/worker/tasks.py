from datetime import datetime, timezone
from uuid import UUID

from spur_api.db.models import ProjectRow, RunEventRow, SimulationRunRow
from spur_api.db.session import get_session_factory
from spur_api.schemas.run import RunStatus
from spur_api.worker.runner import SpurRunner


async def run_simulation(ctx, run_id: str) -> None:
    """The arq job function: run one simulation to completion.

    `ctx["session_factory"]` is set in `WorkerSettings.on_startup` so this
    function (and tests exercising it directly) get one AsyncSession per
    invocation, independent of the FastAPI process's own engine.
    """
    session_factory = ctx.get("session_factory") or get_session_factory()

    async with session_factory() as db:
        run_row = await db.get(SimulationRunRow, UUID(run_id))
        # Run what was submitted, not whatever the project has become since.
        # Runs from before spec_snapshot existed fall back to the live project.
        spec = run_row.spec_snapshot
        if spec is None:
            spec = (await db.get(ProjectRow, run_row.project_id)).spec

        run_row.status = RunStatus.RUNNING
        run_row.started_at = datetime.now(timezone.utc)
        await db.commit()

        seq = 0

        async def on_chunk(sim_time_now, events):
            nonlocal seq
            if events:
                db.add_all(
                    [
                        RunEventRow(
                            run_id=run_row.id,
                            seq=seq + i,
                            time=e.time,
                            event=e.event.value,
                            train_uid=e.train_uid,
                            component_uid=e.component_uid,
                            component_type=e.component_type,
                        )
                        for i, e in enumerate(events)
                    ]
                )
                seq += len(events)
            run_row.sim_time_now = sim_time_now
            await db.commit()

        async def is_cancelled():
            await db.refresh(run_row, attribute_names=["cancel_requested"])
            return run_row.cancel_requested

        runner = SpurRunner(
            spec,
            until=run_row.requested_until,
            chunk_size=run_row.chunk_size,
            seed=run_row.seed,
        )

        try:
            outcome = await runner.run(on_chunk=on_chunk, is_cancelled=is_cancelled)
        except Exception as e:  # noqa: BLE001 - never leave a run stuck in `running`
            run_row.status = RunStatus.FAILED
            run_row.error_message = str(e)
            run_row.finished_at = datetime.now(timezone.utc)
            await db.commit()
            return

        run_row.status = (
            RunStatus.CANCELLED if outcome == "cancelled" else RunStatus.COMPLETED
        )
        run_row.finished_at = datetime.now(timezone.utc)
        await db.commit()
