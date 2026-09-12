from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from spur_api.auth import Principal, current_principal
from spur_api.deps import get_db
from spur_api.schemas.project import Project, ProjectCreate, ProjectUpdate
from spur_api.services import projects_service

router = APIRouter(prefix="/v1/projects", tags=["projects"])


@router.post("", status_code=201)
async def create_project(
    body: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> Project:
    return await projects_service.create_project(db, body, owner=principal.id)


@router.get("")
async def list_projects(db: AsyncSession = Depends(get_db)) -> list[Project]:
    return await projects_service.list_projects(db)


@router.get("/{project_id}")
async def get_project(
    project_id: UUID, db: AsyncSession = Depends(get_db)
) -> Project:
    return await projects_service.get_project(db, project_id)


@router.put("/{project_id}")
async def update_project(
    project_id: UUID,
    body: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
) -> Project:
    return await projects_service.update_project(db, project_id, body)


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: UUID, db: AsyncSession = Depends(get_db)
) -> None:
    await projects_service.delete_project(db, project_id)
