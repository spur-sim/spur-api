"""Simulation execution.

Phase 1 runs a simulation synchronously, in the request-handling process,
with no chunking or progress streaming. This is deliberately the smallest
possible thing that proves the resource model and the spur integration
end-to-end (see the project plan's Phase 1 exit criteria) — Phase 2
replaces this with a real background worker (arq) that chunks execution
via repeated `model.run(until=...)` calls and streams progress, without
changing the `Run`/`SimEvent` shapes this module already produces.
"""

from datetime import datetime, timezone

from spur.core.event import SimEvent
from spur.core.exception import SpurError
from spur.core.model import Model

from spur_api.exceptions import InvalidProjectError
from spur_api.schemas.project import Project
from spur_api.schemas.run import Run, RunStatus
from spur_api.store import InMemoryStore


def _project_dict(project: Project) -> dict:
    # exclude_unset=True matters here, not just for a leaner payload:
    # Model.add_components does `if "jitter" in c.keys()` (and similarly
    # for "collection"), so a key that was never set must be absent from
    # the dict, not present with value None - mirrors what
    # spur.io.formats.read_components_json already does for the same
    # reason.
    return project.model_dump(
        include={"components", "routes", "tours", "trains"},
        mode="json",
        exclude_unset=True,
    )


def execute_run(store: InMemoryStore, run: Run, project: Project) -> Run:
    """Run a simulation to completion and persist the result onto `run`.

    Mutates and returns `run` via the store, transitioning it through
    `running` to a terminal status (`completed` or `failed`).
    """
    run.status = RunStatus.RUNNING
    run.started_at = datetime.now(timezone.utc)
    store.update_run(run)

    events: list[SimEvent] = []
    try:
        model = Model.from_project_dictionary(
            _project_dict(project), event_sink=events.append
        )
    except (SpurError, KeyError, ValueError, TypeError) as e:
        raise InvalidProjectError(f"Could not build a model from project: {e}") from e

    try:
        model.start()
        model.run(until=run.requested_until)
        model.log_current_state()
    except Exception as e:  # noqa: BLE001 - never leave a run stuck in `running`
        run.status = RunStatus.FAILED
        run.error_message = str(e)
        run.finished_at = datetime.now(timezone.utc)
        store.update_run(run)
        store.append_run_events(run.id, events)
        return run

    store.append_run_events(run.id, events)
    run.status = RunStatus.COMPLETED
    run.sim_time_now = model.now
    run.finished_at = datetime.now(timezone.utc)
    return store.update_run(run)
