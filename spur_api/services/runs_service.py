"""Run submission and retrieval.

Actual simulation execution now happens in the background worker (see
`spur_api/worker/tasks.py`) - this module only ever inserts/reads rows and
enqueues jobs, never builds or runs a `Model` itself, keeping the request
path fast regardless of how long a run takes.
"""

from uuid import UUID

from arq import ArqRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spur.core.event import SimEvent, SimEventType

from spur_api.db.models import ProjectRow, RunEventRow, SimulationRunRow
from spur_api.exceptions import NotFoundError
from spur_api.schemas.run import Run, RunStatus


def _to_schema(row: SimulationRunRow) -> Run:
    return Run.model_validate(row, from_attributes=True)


async def submit_run(
    db: AsyncSession,
    redis: ArqRedis,
    project_id: UUID,
    until: int | None,
    chunk_size: int | None,
) -> Run:
    project_row = await db.get(ProjectRow, project_id)
    if project_row is None:
        raise NotFoundError(f"Project {project_id} not found")

    run_row = SimulationRunRow(
        project_id=project_id, requested_until=until, chunk_size=chunk_size
    )
    db.add(run_row)
    await db.commit()
    await db.refresh(run_row)

    job = await redis.enqueue_job("run_simulation", str(run_row.id))
    run_row.arq_job_id = job.job_id if job is not None else None
    await db.commit()
    await db.refresh(run_row)
    return _to_schema(run_row)


async def get_run(db: AsyncSession, run_id: UUID) -> Run:
    row = await db.get(SimulationRunRow, run_id)
    if row is None:
        raise NotFoundError(f"Run {run_id} not found")
    return _to_schema(row)


async def list_runs(
    db: AsyncSession, project_id: UUID | None, status: RunStatus | None
) -> list[Run]:
    stmt = select(SimulationRunRow)
    if project_id is not None:
        stmt = stmt.where(SimulationRunRow.project_id == project_id)
    if status is not None:
        stmt = stmt.where(SimulationRunRow.status == status)
    result = await db.execute(stmt)
    return [_to_schema(r) for r in result.scalars().all()]


async def delete_run(db: AsyncSession, run_id: UUID) -> None:
    row = await db.get(SimulationRunRow, run_id)
    if row is None:
        raise NotFoundError(f"Run {run_id} not found")
    await db.delete(row)
    await db.commit()


async def request_cancel(db: AsyncSession, run_id: UUID) -> Run:
    """Flag a run for cooperative cancellation.

    The worker checks this flag between chunks (see
    `spur_api/worker/tasks.py::is_cancelled`), so cancellation is not
    instantaneous - a run already past its last chunk boundary before
    the flag is set will still finish normally.
    """
    row = await db.get(SimulationRunRow, run_id)
    if row is None:
        raise NotFoundError(f"Run {run_id} not found")
    row.cancel_requested = True
    await db.commit()
    await db.refresh(row)
    return _to_schema(row)


async def get_run_events(
    db: AsyncSession,
    run_id: UUID,
    since_time: int | None = None,
    train_uid: str | None = None,
    component_uid: str | None = None,
    event_type: SimEventType | None = None,
    limit: int = 1000,
    offset: int = 0,
) -> list[SimEvent]:
    run_row = await db.get(SimulationRunRow, run_id)
    if run_row is None:
        raise NotFoundError(f"Run {run_id} not found")

    stmt = select(RunEventRow).where(RunEventRow.run_id == run_id).order_by(
        RunEventRow.seq
    )
    if since_time is not None:
        stmt = stmt.where(RunEventRow.time >= since_time)
    if train_uid is not None:
        stmt = stmt.where(RunEventRow.train_uid == train_uid)
    if component_uid is not None:
        stmt = stmt.where(RunEventRow.component_uid == component_uid)
    if event_type is not None:
        stmt = stmt.where(RunEventRow.event == event_type.value)
    stmt = stmt.offset(offset).limit(limit)

    result = await db.execute(stmt)
    return [
        SimEvent(
            time=r.time,
            event=r.event,
            train_uid=r.train_uid,
            component_uid=r.component_uid,
            component_type=r.component_type,
        )
        for r in result.scalars().all()
    ]
