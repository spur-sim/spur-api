from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from spur_api.db.models import ProjectRow
from spur_api.exceptions import NotFoundError
from spur_api.schemas.project import (
    Project,
    ProjectCounts,
    ProjectCreate,
    ProjectSummary,
)


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


async def list_projects(
    db: AsyncSession, limit: int = 100, offset: int = 0
) -> list[ProjectSummary]:
    # Selects only the small columns and counts each spec section in SQL, so
    # listing never loads the (large) spec of every project.
    def count(section: str):
        return func.coalesce(func.jsonb_array_length(ProjectRow.spec[section]), 0)

    stmt = (
        select(
            ProjectRow.id,
            ProjectRow.name,
            ProjectRow.spur_version,
            ProjectRow.owner,
            ProjectRow.created_at,
            ProjectRow.updated_at,
            count("components").label("components"),
            count("routes").label("routes"),
            count("tours").label("tours"),
            count("trains").label("trains"),
        )
        .order_by(ProjectRow.created_at.desc(), ProjectRow.id)
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return [
        ProjectSummary(
            id=r.id,
            name=r.name,
            spur_version=r.spur_version,
            owner=r.owner,
            created_at=r.created_at,
            updated_at=r.updated_at,
            counts=ProjectCounts(
                components=r.components,
                routes=r.routes,
                tours=r.tours,
                trains=r.trains,
            ),
        )
        for r in result.all()
    ]


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
