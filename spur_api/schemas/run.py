from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field, model_validator

from spur.analysis import ComponentStats, RunStats, TrainStats

# numpy's default_rng accepts any non-negative integer; the DB column is a
# signed 64-bit BigInteger.
MAX_SEED = 2**63 - 1


# How many runs one submission can ask for.
MAX_SEEDS = 100

MAX_RUN_NAME_LENGTH = 200


def _blank_is_none(value):
    # A name of only spaces is no name. Trimming happens here, before the
    # length check, so padding doesn't count against the limit.
    if isinstance(value, str):
        return value.strip() or None
    return value


# What a person calls a run ("Baseline, new timetable"). Optional: a run
# without one is known by when it was submitted and its seed.
RunName = Annotated[
    Annotated[str, Field(max_length=MAX_RUN_NAME_LENGTH)] | None,
    BeforeValidator(_blank_is_none),
]


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
    # How many runs to make. More than one makes a batch: runs that differ
    # only in their seed, which counts up from `seed` (or from one the
    # server picks), so the whole batch can be replayed from its first seed.
    seeds: int = Field(default=1, ge=1, le=MAX_SEEDS)
    name: RunName = None

    @model_validator(mode="after")
    def _seeds_fit(self):
        if self.seed is not None and self.seed + self.seeds - 1 > MAX_SEED:
            raise ValueError(
                f"seed is too large to count {self.seeds} seeds up from it"
            )
        return self


class RunUpdate(BaseModel):
    """Request body for renaming a run. A null or blank name removes it."""

    name: RunName


class Run(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    name: str | None = None
    # The project's `version` when the run was submitted. If it is lower
    # than the project's `inputs_version`, what the simulation reads has
    # been edited since and the run's results describe the earlier state.
    # Null for runs made before versions existed.
    project_version: int | None = None
    status: RunStatus = RunStatus.QUEUED
    requested_until: int | None = None
    until_target: int | None = None
    seed: int | None = None
    # Shared by the runs of one submission that asked for several seeds.
    # Null for a run submitted on its own.
    batch_id: UUID | None = None
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
