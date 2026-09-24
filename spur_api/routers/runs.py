from uuid import UUID

from arq import ArqRedis
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from spur.analysis import Visit
from spur.core.event import SimEvent, SimEventType

from spur_api.deps import get_db, get_redis
from spur_api.schemas.run import Run, RunCreate, RunStatus, RunSummary
from spur_api.services import runs_service

router = APIRouter(tags=["runs"])


@router.post("/v1/projects/{project_id}/runs", status_code=202)
async def submit_run(
    project_id: UUID,
    body: RunCreate,
    db: AsyncSession = Depends(get_db),
    redis: ArqRedis = Depends(get_redis),
) -> Run:
    return await runs_service.submit_run(
        db,
        redis,
        project_id,
        until=body.until,
        chunk_size=body.chunk_size,
        seed=body.seed,
    )


@router.get("/v1/runs/{run_id}")
async def get_run(run_id: UUID, db: AsyncSession = Depends(get_db)) -> Run:
    return await runs_service.get_run(db, run_id)


@router.get("/v1/runs")
async def list_runs(
    project_id: UUID | None = None,
    status: RunStatus | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[Run]:
    return await runs_service.list_runs(db, project_id=project_id, status=status)


@router.post("/v1/runs/{run_id}/cancel")
async def cancel_run(run_id: UUID, db: AsyncSession = Depends(get_db)) -> Run:
    return await runs_service.request_cancel(db, run_id)


@router.delete("/v1/runs/{run_id}", status_code=204)
async def delete_run(run_id: UUID, db: AsyncSession = Depends(get_db)) -> None:
    await runs_service.delete_run(db, run_id)


@router.get("/v1/runs/{run_id}/events")
async def get_run_events(
    run_id: UUID,
    since_time: int | None = None,
    train_uid: str | None = None,
    component_uid: str | None = None,
    event_type: SimEventType | None = None,
    limit: int = Query(default=1000, le=10000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[SimEvent]:
    return await runs_service.get_run_events(
        db,
        run_id,
        since_time=since_time,
        train_uid=train_uid,
        component_uid=component_uid,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )


@router.get("/v1/runs/{run_id}/summary")
async def get_run_summary(
    run_id: UUID,
    on_time_threshold: int = Query(default=120, ge=0),
    db: AsyncSession = Depends(get_db),
) -> RunSummary:
    return await runs_service.get_run_summary(db, run_id, on_time_threshold)


@router.get("/v1/runs/{run_id}/visits")
async def get_run_visits(
    run_id: UUID,
    train_uid: str | None = None,
    component_uid: str | None = None,
    limit: int = Query(default=1000, ge=1, le=10000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[Visit]:
    return await runs_service.get_run_visits(
        db,
        run_id,
        train_uid=train_uid,
        component_uid=component_uid,
        limit=limit,
        offset=offset,
    )
