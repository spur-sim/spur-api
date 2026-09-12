from uuid import UUID

from fastapi import APIRouter, Depends, Query

from spur.core.event import SimEvent, SimEventType

from spur_api.deps import get_store
from spur_api.schemas.run import Run, RunCreate, RunStatus
from spur_api.services.runs_service import execute_run
from spur_api.store import InMemoryStore

router = APIRouter(tags=["runs"])


@router.post("/v1/projects/{project_id}/runs", status_code=201)
def submit_run(
    project_id: UUID,
    body: RunCreate,
    store: InMemoryStore = Depends(get_store),
) -> Run:
    project = store.get_project(project_id)  # 404s if missing
    run = store.create_run(Run(project_id=project.id, requested_until=body.until))
    # Phase 1: executed synchronously in-request. Phase 2 replaces this
    # call with enqueuing a background job and returning immediately with
    # status=queued - see spur_api/services/runs_service.py.
    return execute_run(store, run, project)


@router.get("/v1/runs/{run_id}")
def get_run(run_id: UUID, store: InMemoryStore = Depends(get_store)) -> Run:
    return store.get_run(run_id)


@router.get("/v1/runs")
def list_runs(
    project_id: UUID | None = None,
    status: RunStatus | None = None,
    store: InMemoryStore = Depends(get_store),
) -> list[Run]:
    runs = store.list_runs(project_id=project_id)
    if status is not None:
        runs = [r for r in runs if r.status == status]
    return runs


@router.delete("/v1/runs/{run_id}", status_code=204)
def delete_run(run_id: UUID, store: InMemoryStore = Depends(get_store)) -> None:
    store.delete_run(run_id)


@router.get("/v1/runs/{run_id}/events")
def get_run_events(
    run_id: UUID,
    since_time: int | None = None,
    train_uid: str | None = None,
    component_uid: str | None = None,
    event_type: SimEventType | None = None,
    limit: int = Query(default=1000, le=10000),
    offset: int = Query(default=0, ge=0),
    store: InMemoryStore = Depends(get_store),
) -> list[SimEvent]:
    events = store.get_run_events(run_id)  # 404s if run missing
    if since_time is not None:
        events = [e for e in events if e.time >= since_time]
    if train_uid is not None:
        events = [e for e in events if e.train_uid == train_uid]
    if component_uid is not None:
        events = [e for e in events if e.component_uid == component_uid]
    if event_type is not None:
        events = [e for e in events if e.event == event_type]
    return events[offset : offset + limit]
