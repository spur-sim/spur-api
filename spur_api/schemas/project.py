"""Project resource schemas.

Deliberately thin: `ProjectSpec` (from `spur.io.schema`) already defines
the exact component/route/tour/train shape spur itself accepts, so a
project *is* a `ProjectSpec` plus API-owned metadata (id, timestamps) —
not a reinvented resource model.
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import Field

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
