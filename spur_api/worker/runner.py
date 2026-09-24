"""Chunked spur simulation execution.

This is the only module that imports `spur` directly - isolating future
spur-version bumps (and any future changes to `Model`'s constructor or
`event_sink` contract) to one obvious place, per the project plan.
"""

from typing import Awaitable, Callable

from spur.core.event import SimEvent
from spur.core.exception import SpurError
from spur.core.model import Model

from spur_api.config import settings
from spur_api.exceptions import InvalidProjectError

OnChunk = Callable[[int, list[SimEvent]], Awaitable[None]]
IsCancelled = Callable[[], Awaitable[bool]]


class SpurRunner:
    """Runs one project to completion (or cancellation) via repeated,
    bounded `model.run(until=...)` calls, so a caller can persist/publish
    progress and check for cancellation between chunks without needing
    `spur` itself to support pausing mid-run.

    Parameters
    ----------
    project_dict : dict
        A dict with "components"/"routes"/"tours"/"trains" keys, in the
        shape `Model.from_project_dictionary` expects.
    until : int, optional
        The simulation clock value to run to. If None, derived from the
        latest `deletion_time` across the project's tours (falling back to
        `settings.default_run_horizon` if there are none).
    chunk_size : int, optional
        Sim-time units per `model.run(until=...)` call. If None, derived
        so the run produces roughly `settings.default_chunk_count` chunks.
    seed : int, optional
        Seeds the model's random number generator; the same project and
        seed reproduce the same run. If None, the run is not reproducible.
    """

    def __init__(
        self,
        project_dict: dict,
        until: int | None = None,
        chunk_size: int | None = None,
        seed: int | None = None,
    ) -> None:
        self._project_dict = project_dict
        self.until = until
        self.chunk_size = chunk_size
        self.seed = seed

    def _build_model(self, event_sink: Callable[[SimEvent], None]) -> Model:
        try:
            return Model.from_project_dictionary(
                self._project_dict, event_sink=event_sink, seed=self.seed
            )
        except (SpurError, KeyError, ValueError, TypeError) as e:
            raise InvalidProjectError(
                f"Could not build a model from project: {e}"
            ) from e

    @staticmethod
    def _derive_until(model: Model) -> int:
        deletion_times = [t.deletion_time for t in model._tours.values()]
        return max(deletion_times, default=settings.default_run_horizon)

    async def run(self, on_chunk: OnChunk, is_cancelled: IsCancelled) -> str:
        """Run to completion or cancellation.

        `on_chunk(sim_time_now, events)` is awaited after every chunk
        (including a final flush after `log_current_state()`), even when
        `events` is empty, so a caller can track `sim_time_now` progress
        independent of event volume. `is_cancelled()` is awaited before
        each chunk; returning True stops the run early without processing
        further chunks (the events already produced up to that point are
        still flushed via a final `on_chunk` call).

        Returns "completed" or "cancelled".
        """
        events_batch: list[SimEvent] = []
        model = self._build_model(events_batch.append)
        model.start()

        until_target = self.until if self.until is not None else self._derive_until(model)
        chunk = self.chunk_size or max(1, until_target // settings.default_chunk_count)

        while model.now < until_target:
            if await is_cancelled():
                await on_chunk(model.now, list(events_batch))
                return "cancelled"
            next_checkpoint = min(model.now + chunk, until_target)
            model.run(until=next_checkpoint)
            await on_chunk(model.now, list(events_batch))
            events_batch.clear()

        model.log_current_state()
        await on_chunk(model.now, list(events_batch))
        return "completed"
