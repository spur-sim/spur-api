from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends

from spur_api.auth import Principal, current_principal
from spur_api.deps import get_store
from spur_api.schemas.project import Project, ProjectCreate, ProjectUpdate
from spur_api.store import InMemoryStore

router = APIRouter(prefix="/v1/projects", tags=["projects"])


@router.post("", status_code=201)
def create_project(
    body: ProjectCreate,
    store: InMemoryStore = Depends(get_store),
    principal: Principal = Depends(current_principal),
) -> Project:
    # exclude_unset=True preserves which nested fields (e.g. a component's
    # jitter/collection) were actually present in the request body, all
    # the way through to the Model this project eventually builds - see
    # spur_api/services/runs_service.py::_project_dict for why that
    # matters.
    project = Project(**body.model_dump(exclude_unset=True), owner=principal.id)
    return store.create_project(project)


@router.get("")
def list_projects(store: InMemoryStore = Depends(get_store)) -> list[Project]:
    return store.list_projects()


@router.get("/{project_id}")
def get_project(project_id: UUID, store: InMemoryStore = Depends(get_store)) -> Project:
    return store.get_project(project_id)


@router.put("/{project_id}")
def update_project(
    project_id: UUID,
    body: ProjectUpdate,
    store: InMemoryStore = Depends(get_store),
) -> Project:
    existing = store.get_project(project_id)
    # Rebuilt via the constructor (not model_copy's update=), so the new
    # spec fields are properly re-validated into ComponentSpec/RouteSpec/
    # etc. instances rather than left as plain dicts.
    updated = Project(
        **body.model_dump(exclude_unset=True),
        id=existing.id,
        owner=existing.owner,
        created_at=existing.created_at,
        updated_at=datetime.now(timezone.utc),
    )
    return store.update_project(updated)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: UUID, store: InMemoryStore = Depends(get_store)) -> None:
    store.delete_project(project_id)
