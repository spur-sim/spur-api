"""In-memory persistence, Phase 1 only.

This is deliberately not the real data layer — Phase 2 replaces it with
Postgres (SQLAlchemy models under `spur_api/db/`, see the project plan).
Keeping it isolated to one module makes that swap a matter of changing
what `spur_api/deps.py` hands to routers, not touching router code.
"""

from threading import Lock
from uuid import UUID

from spur.core.event import SimEvent

from spur_api.exceptions import NotFoundError
from spur_api.schemas.project import Project
from spur_api.schemas.run import Run


class InMemoryStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._projects: dict[UUID, Project] = {}
        self._runs: dict[UUID, Run] = {}
        self._run_events: dict[UUID, list[SimEvent]] = {}

    # Projects
    def create_project(self, project: Project) -> Project:
        with self._lock:
            self._projects[project.id] = project
        return project

    def get_project(self, project_id: UUID) -> Project:
        try:
            return self._projects[project_id]
        except KeyError:
            raise NotFoundError(f"Project {project_id} not found") from None

    def list_projects(self) -> list[Project]:
        return list(self._projects.values())

    def update_project(self, project: Project) -> Project:
        with self._lock:
            if project.id not in self._projects:
                raise NotFoundError(f"Project {project.id} not found")
            self._projects[project.id] = project
        return project

    def delete_project(self, project_id: UUID) -> None:
        with self._lock:
            if project_id not in self._projects:
                raise NotFoundError(f"Project {project_id} not found")
            del self._projects[project_id]

    # Runs
    def create_run(self, run: Run) -> Run:
        with self._lock:
            self._runs[run.id] = run
            self._run_events[run.id] = []
        return run

    def get_run(self, run_id: UUID) -> Run:
        try:
            return self._runs[run_id]
        except KeyError:
            raise NotFoundError(f"Run {run_id} not found") from None

    def list_runs(self, project_id: UUID | None = None) -> list[Run]:
        runs = list(self._runs.values())
        if project_id is not None:
            runs = [r for r in runs if r.project_id == project_id]
        return runs

    def update_run(self, run: Run) -> Run:
        with self._lock:
            if run.id not in self._runs:
                raise NotFoundError(f"Run {run.id} not found")
            self._runs[run.id] = run
        return run

    def delete_run(self, run_id: UUID) -> None:
        with self._lock:
            if run_id not in self._runs:
                raise NotFoundError(f"Run {run_id} not found")
            del self._runs[run_id]
            del self._run_events[run_id]

    def append_run_events(self, run_id: UUID, events: list[SimEvent]) -> None:
        with self._lock:
            self._run_events[run_id].extend(events)

    def get_run_events(self, run_id: UUID) -> list[SimEvent]:
        if run_id not in self._run_events:
            raise NotFoundError(f"Run {run_id} not found")
        return list(self._run_events[run_id])


# Process-wide singleton for Phase 1. Replaced by a DB session dependency
# in Phase 2.
store = InMemoryStore()
