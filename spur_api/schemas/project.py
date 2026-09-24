"""Project resource schemas.

Deliberately thin: `ProjectSpec` (from `spur.io.schema`) already defines
the exact component/route/tour/train shape spur itself accepts, so a
project *is* a `ProjectSpec` plus API-owned metadata (id, timestamps) —
not a reinvented resource model.
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from typing import Literal, Optional

from pydantic import BaseModel, Field

from spur.io.schema import ProjectSpec


class ProjectCreate(ProjectSpec):
    """Request body for creating a project: exactly a `ProjectSpec`."""


class ProjectUpdate(ProjectSpec):
    """Request body for replacing a project: exactly a `ProjectSpec`."""


class Project(ProjectSpec):
    """A stored project: a `ProjectSpec` plus API metadata."""

    id: UUID = Field(default_factory=uuid4)
    owner: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProjectCounts(BaseModel):
    components: int
    routes: int
    tours: int
    trains: int


class ProjectSummary(BaseModel):
    """A project without its spec: enough to show in a list. Fetch
    `GET /v1/projects/{id}` for the full spec."""

    id: UUID
    name: str | None = None
    spur_version: str
    owner: str | None = None
    created_at: datetime
    updated_at: datetime
    counts: ProjectCounts


class ProjectEnvelope(BaseModel):
    """The fields of a project that `POST /v1/projects` requires besides the
    four sections, which `spur.validation.validate` checks. Together they mean
    exactly what `ProjectSpec` accepts."""

    type: Literal["SpurProject"]
    spur_version: str
    name: Optional[str] = None
