from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunCreate(BaseModel):
    """Request body for submitting a simulation run.

    `until` mirrors `Model.run(until=...)` — the simulation clock value to
    run to (None runs to completion). `chunk_size` is accepted by the API
    surface from Phase 1 onward for forward compatibility, but has no
    effect until Phase 2's background worker actually chunks execution for
    progress reporting; Phase 1 always runs to `until` in one step.
    """

    until: int | None = None
    chunk_size: int | None = None


class Run(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    status: RunStatus = RunStatus.QUEUED
    requested_until: int | None = None
    sim_time_now: int | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    finished_at: datetime | None = None
