from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from spur_api.db.models import ProjectRow
from spur_api.exceptions import NotFoundError, StaleProjectError
from spur_api.schemas.project import (
    Project,
    ProjectCounts,
    ProjectCreate,
    ProjectSummary,
)


# The sections of a project that a simulation reads. The rest (its name,
# `extensions`) can change without changing what a run would produce.
_SIMULATION_INPUTS = ("components", "routes", "tours", "trains")


def _to_schema(row: ProjectRow) -> Project:
    return Project(
        **row.spec,
        id=row.id,
        owner=row.owner,
        version=row.version,
        inputs_version=row.inputs_version,
        base_project_id=row.base_project_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def create_project(
    db: AsyncSession,
    spec: ProjectCreate,
    owner: str | None,
    base_project_id: UUID | None = None,
) -> Project:
    """Store a project. With `base_project_id` it is a scenario of that
    project, or of that project's own base if it is a scenario itself, so
    that every scenario of a family points at the one base."""
    base_id = None
    if base_project_id is not None:
        base = await db.get(ProjectRow, base_project_id)
        if base is None:
            raise NotFoundError(f"Project {base_project_id} not found")
        base_id = base.base_project_id or base.id
    spec_dict = spec.model_dump(exclude_unset=True)
    row = ProjectRow(
        owner=owner,
        name=spec.name,
        spur_version=spec.spur_version,
        spec=spec_dict,
        base_project_id=base_id,
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
    db: AsyncSession,
    limit: int = 100,
    offset: int = 0,
    base_project_id: UUID | None = None,
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
            ProjectRow.base_project_id,
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
    if base_project_id is not None:
        stmt = stmt.where(ProjectRow.base_project_id == base_project_id)
    result = await db.execute(stmt)
    return [
        ProjectSummary(
            id=r.id,
            name=r.name,
            spur_version=r.spur_version,
            owner=r.owner,
            base_project_id=r.base_project_id,
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
    db: AsyncSession,
    project_id: UUID,
    spec: ProjectCreate,
    expected_version: int | None = None,
) -> Project:
    """Replace a project's spec.

    With `expected_version`, the save goes ahead only if that is still the
    project's version; otherwise someone else has saved since the caller
    loaded it, and the save is refused rather than overwrite their work.
    Without it the save always goes ahead.
    """
    # Locked so that two saves carrying the same version can't both pass the
    # check: the second waits here and then sees the first one's new version.
    row = await db.get(ProjectRow, project_id, with_for_update=True)
    if row is None:
        raise NotFoundError(f"Project {project_id} not found")
    if expected_version is not None and expected_version != row.version:
        raise StaleProjectError(
            f"Project {project_id} is at version {row.version}, not {expected_version}",
            version=row.version,
        )
    row.version += 1
    new_spec = spec.model_dump(exclude_unset=True)
    if any(new_spec.get(s) != row.spec.get(s) for s in _SIMULATION_INPUTS):
        row.inputs_version = row.version
    row.name = spec.name
    row.spur_version = spec.spur_version
    row.spec = new_spec
    await db.commit()
    await db.refresh(row)
    return _to_schema(row)


async def delete_project(db: AsyncSession, project_id: UUID) -> None:
    row = await db.get(ProjectRow, project_id)
    if row is None:
        raise NotFoundError(f"Project {project_id} not found")
    await db.delete(row)
    await db.commit()
