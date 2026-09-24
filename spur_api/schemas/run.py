from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from spur.analysis import ComponentStats, RunStats, TrainStats

# numpy's default_rng accepts any non-negative integer; the DB column is a
# signed 64-bit BigInteger.
MAX_SEED = 2**63 - 1


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunCreate(BaseModel):
    """Request body for submitting a simulation run.

    `until` is the simulation clock value to run to; if omitted, the run
    goes to the latest tour deletion_time in the project. `chunk_size` is
    the sim-time per progress checkpoint; if omitted, about 100 chunks.
    """

    until: int | None = None
    chunk_size: int | None = None
    # Same project + same seed gives an identical run. If omitted, the
    # server picks one and records it on the run, so any run can be
    # replayed later by resubmitting with that seed.
    seed: int | None = Field(default=None, ge=0, le=MAX_SEED)


class Run(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    status: RunStatus = RunStatus.QUEUED
    requested_until: int | None = None
    until_target: int | None = None
    seed: int | None = None
    sim_time_now: int | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    finished_at: datetime | None = None


class RunSummary(BaseModel):
    """Aggregate metrics for a run, computed by `spur.analysis.analyze`.

    `status` says how far the run got: a run that is still running, or was
    cancelled or failed, reports the metrics of the events it has produced.
    """

    status: RunStatus
    run: RunStats
    components: list[ComponentStats]
    trains: list[TrainStats]
