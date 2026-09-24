"""Exercises SpurRunner directly - no DB, no arq, no HTTP - so its chunking
and cancellation behavior can be tested independent of the persistence
layer built on top of it in spur_api/worker/tasks.py.
"""

from spur_api.worker.runner import SpurRunner


def _project_dict(line4_project_dict):
    return {
        k: line4_project_dict[k]
        for k in ("components", "routes", "tours", "trains")
    }


async def test_chunked_run_matches_single_shot_event_count(line4_project_dict):
    project = _project_dict(line4_project_dict)

    chunks_seen = []

    async def on_chunk(sim_time_now, events):
        chunks_seen.append((sim_time_now, list(events)))

    async def never_cancelled():
        return False

    # The fixture includes a DisruptionJitter, so without a seed two runs
    # can differ purely from random draws. Giving both the same seed
    # isolates what this test checks: that chunking a run into several
    # `model.run(until=...)` calls gives identical output to a single call.
    runner = SpurRunner(project, until=3600, chunk_size=360, seed=12345)
    outcome = await runner.run(on_chunk=on_chunk, is_cancelled=never_cancelled)

    assert outcome == "completed"
    # 3600 / 360 = 10 run(until=...) chunks, plus one final flush chunk
    # after log_current_state() - see SpurRunner.run().
    assert len(chunks_seen) == 11
    assert chunks_seen[-1][0] == 3600

    all_events = [e for _, batch in chunks_seen for e in batch]

    # Regression guard: chunking must not drop or duplicate events
    # compared to running the same project to the same `until` in one
    # single-call model.run(), matching Phase 1's in-process behaviour.
    from spur.core.model import Model

    reference_events = []
    m = Model.from_project_dictionary(
        project, event_sink=reference_events.append, seed=12345
    )
    m.start()
    m.run(until=3600)
    m.log_current_state()

    assert [e.model_dump() for e in all_events] == [
        e.model_dump() for e in reference_events
    ]


async def test_cancellation_stops_before_until_target(line4_project_dict):
    project = _project_dict(line4_project_dict)

    async def on_chunk(sim_time_now, events):
        pass

    async def always_cancelled():
        return True

    runner = SpurRunner(project, until=3600, chunk_size=360)
    outcome = await runner.run(on_chunk=on_chunk, is_cancelled=always_cancelled)

    assert outcome == "cancelled"


async def test_derives_until_from_tour_deletion_times(line4_project_dict):
    project = _project_dict(line4_project_dict)
    max_deletion_time = max(t["deletion_time"] for t in project["tours"])

    seen_final_time = None

    async def on_chunk(sim_time_now, events):
        nonlocal seen_final_time
        seen_final_time = sim_time_now

    async def never_cancelled():
        return False

    runner = SpurRunner(project, until=None, chunk_size=3600)
    await runner.run(on_chunk=on_chunk, is_cancelled=never_cancelled)

    assert seen_final_time == max_deletion_time


async def test_same_seed_reproduces_a_full_day_run_and_different_seed_differs(
    line4_project_dict,
):
    project = _project_dict(line4_project_dict)

    async def run(seed):
        events = []

        async def on_chunk(sim_time_now, batch):
            events.extend(e.model_dump() for e in batch)

        async def never_cancelled():
            return False

        await SpurRunner(project, until=36900, seed=seed).run(
            on_chunk=on_chunk, is_cancelled=never_cancelled
        )
        return events

    assert await run(7) == await run(7)
    assert await run(7) != await run(8)
