from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spur_api.db.models import ProjectRow
from spur_api.exceptions import NotFoundError
from spur_api.schemas.project import Project, ProjectCreate


def _to_schema(row: ProjectRow) -> Project:
    return Project(
        **row.spec, id=row.id, owner=row.owner, created_at=row.created_at, updated_at=row.updated_at
    )


async def create_project(
    db: AsyncSession, spec: ProjectCreate, owner: str | None
) -> Project:
    spec_dict = spec.model_dump(exclude_unset=True)
    row = ProjectRow(
        owner=owner, name=spec.name, spur_version=spec.spur_version, spec=spec_dict
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _to_schema(row)


async def get_project(db: AsyncSession, project_id: UUID) -> Project:
    row = await db.get(ProjectRow, project_id)
    if row is None:
        raise NotFoundError(f"Project {project_id} not found")
    return _to_schema(row)


async def list_projects(db: AsyncSession) -> list[Project]:
    result = await db.execute(select(ProjectRow))
    return [_to_schema(r) for r in result.scalars().all()]


async def update_project(
    db: AsyncSession, project_id: UUID, spec: ProjectCreate
) -> Project:
    row = await db.get(ProjectRow, project_id)
    if row is None:
        raise NotFoundError(f"Project {project_id} not found")
    row.name = spec.name
    row.spur_version = spec.spur_version
    row.spec = spec.model_dump(exclude_unset=True)
    await db.commit()
    await db.refresh(row)
    return _to_schema(row)


async def delete_project(db: AsyncSession, project_id: UUID) -> None:
    row = await db.get(ProjectRow, project_id)
    if row is None:
        raise NotFoundError(f"Project {project_id} not found")
    await db.delete(row)
    await db.commit()
