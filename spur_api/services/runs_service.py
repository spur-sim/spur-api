"""Run submission and retrieval.

Actual simulation execution now happens in the background worker (see
`spur_api/worker/tasks.py`) - this module only ever inserts/reads rows and
enqueues jobs, never builds or runs a `Model` itself, keeping the request
path fast regardless of how long a run takes.
"""

import secrets
from uuid import UUID

from arq import ArqRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spur.analysis import Visit, analyze
from spur.core.event import SimEvent, SimEventType
from spur.core.exception import InputMismatchError
from spur.validation import validate

from spur_api.db.models import ProjectRow, RunEventRow, SimulationRunRow
from spur_api.exceptions import (
    NotFoundError,
    ProjectInvalidError,
    RunAnalysisError,
    RunNotReadyError,
)
from spur_api.schemas.run import MAX_SEED, Run, RunStatus, RunSummary
from spur_api.worker.runner import derive_until


def _to_schema(row: SimulationRunRow) -> Run:
    return Run.model_validate(row, from_attributes=True)


def _event_from_row(row: RunEventRow) -> SimEvent:
    return SimEvent(
        time=row.time,
        event=row.event,
        train_uid=row.train_uid,
        component_uid=row.component_uid,
        component_type=row.component_type,
    )


async def submit_run(
    db: AsyncSession,
    redis: ArqRedis,
    project_id: UUID,
    until: int | None,
    chunk_size: int | None,
    seed: int | None = None,
) -> Run:
    project_row = await db.get(ProjectRow, project_id)
    if project_row is None:
        raise NotFoundError(f"Project {project_id} not found")

    # Saving a project is permissive so drafts can be stored, so check it here
    # rather than queue a run that is certain to fail. This also covers
    # projects saved before validation existed. Warnings don't block a run.
    result = validate(project_row.spec)
    if not result.valid:
        errors = sum(i.severity == "error" for i in result.issues)
        raise ProjectInvalidError(
            f"Project {project_id} has {errors} error(s), so it can't be run", result.issues
        )

    if seed is None:
        # Always record a seed, even when the caller didn't ask for one, so
        # any run can be replayed exactly by resubmitting with it.
        seed = secrets.randbelow(MAX_SEED + 1)

    run_row = SimulationRunRow(
        project_id=project_id,
        requested_until=until,
        until_target=until if until is not None else derive_until(project_row.spec),
        chunk_size=chunk_size,
        seed=seed,
        spec_snapshot=project_row.spec,
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
    return [_event_from_row(r) for r in result.scalars().all()]


async def _analyze_run(db: AsyncSession, run_id: UUID, on_time_threshold: int):
    run_row = await db.get(SimulationRunRow, run_id)
    if run_row is None:
        raise NotFoundError(f"Run {run_id} not found")
    if run_row.status == RunStatus.QUEUED:
        raise RunNotReadyError(f"Run {run_id} is still queued and has no results yet")

    # Analyse against the spec the run actually used. Runs from before
    # spec_snapshot existed fall back to the live project.
    spec = run_row.spec_snapshot
    if spec is None:
        spec = (await db.get(ProjectRow, run_row.project_id)).spec

    result = await db.execute(
        select(RunEventRow).where(RunEventRow.run_id == run_id).order_by(RunEventRow.seq)
    )
    events = [_event_from_row(r) for r in result.scalars().all()]
    try:
        return run_row.status, analyze(events, spec, on_time_threshold)
    except InputMismatchError as e:
        raise RunAnalysisError(
            f"Run {run_id}'s events do not match its project: {e}"
        ) from e


async def get_run_summary(
    db: AsyncSession, run_id: UUID, on_time_threshold: int
) -> RunSummary:
    status, analysis = await _analyze_run(db, run_id, on_time_threshold)
    return RunSummary(
        status=status,
        run=analysis.run,
        components=analysis.components,
        trains=analysis.trains,
    )


async def get_run_visits(
    db: AsyncSession,
    run_id: UUID,
    train_uid: str | None = None,
    component_uid: str | None = None,
    limit: int = 1000,
    offset: int = 0,
) -> list[Visit]:
    _, analysis = await _analyze_run(db, run_id, on_time_threshold=120)
    visits = analysis.visits
    if train_uid is not None:
        visits = [v for v in visits if v.train_uid == train_uid]
    if component_uid is not None:
        visits = [v for v in visits if v.component_uid == component_uid]
    return visits[offset : offset + limit]
