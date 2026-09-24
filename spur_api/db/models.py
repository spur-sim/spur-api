import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from spur_api.db.base import Base
from spur_api.schemas.run import RunStatus

# Every timestamp column is timezone-aware: application code writes
# datetime.now(timezone.utc) throughout (see schemas/project.py,
# schemas/run.py, worker/tasks.py), and asyncpg rejects mixing aware and
# naive datetimes against the same column.
UTCDateTime = DateTime(timezone=True)


class ProjectRow(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner: Mapped[str | None] = mapped_column(nullable=True)
    name: Mapped[str | None] = mapped_column(nullable=True)
    spur_version: Mapped[str] = mapped_column()
    # The full validated ProjectSpec dict (type/name/spur_version/
    # components/routes/tours/trains), exactly as spur.io.formats would
    # produce it - see spur_api/services/projects_service.py. `name` and
    # `spur_version` are duplicated as their own columns for querying
    # without a JSON path expression; `spec` remains the source of truth.
    spec: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), onupdate=func.now()
    )


class SimulationRunRow(Base):
    __tablename__ = "simulation_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE")
    )
    status: Mapped[RunStatus] = mapped_column(default=RunStatus.QUEUED)
    requested_until: Mapped[int | None] = mapped_column(nullable=True)
    # The simulation time the run will go to: requested_until if given, else
    # derived from the project's tours when the run was submitted. Lets a
    # client show progress as sim_time_now / until_target. Null for runs
    # created before this column existed.
    until_target: Mapped[int | None] = mapped_column(nullable=True)
    chunk_size: Mapped[int | None] = mapped_column(nullable=True)
    seed: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # A copy of the project spec taken when the run was submitted. Delays are
    # measured against the schedule, and a project can be edited after a run,
    # so the run's events must be analysed against what it actually ran.
    # Nullable: runs from before this column existed fall back to the live
    # project.
    spec_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    sim_time_now: Mapped[int | None] = mapped_column(nullable=True)
    arq_job_id: Mapped[str | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class RunEventRow(Base):
    __tablename__ = "run_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("simulation_runs.id", ondelete="CASCADE")
    )
    # Monotonic per-run ordering, assigned by the worker as it drains
    # batches - cheaper to sort/index on than time+event-type ties, since
    # several events share the same `time`.
    seq: Mapped[int] = mapped_column()
    time: Mapped[int] = mapped_column()
    event: Mapped[str] = mapped_column()
    train_uid: Mapped[str] = mapped_column()
    component_uid: Mapped[str] = mapped_column()
    component_type: Mapped[str] = mapped_column()

    __table_args__ = (
        Index("ix_run_events_run_id_seq", "run_id", "seq", unique=True),
        Index("ix_run_events_run_id_train_uid", "run_id", "train_uid"),
        Index("ix_run_events_run_id_component_uid", "run_id", "component_uid"),
    )
