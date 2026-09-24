import pytest


async def _create_project(client, line4_project_dict):
    resp = await client.post("/v1/projects", json=line4_project_dict)
    assert resp.status_code == 201
    return resp.json()["id"]


async def test_submit_run_returns_queued_immediately(client, line4_project_dict):
    project_id = await _create_project(client, line4_project_dict)

    resp = await client.post(f"/v1/projects/{project_id}/runs", json={"until": 3600})
    assert resp.status_code == 202
    run = resp.json()
    assert run["status"] == "queued"
    assert run["project_id"] == project_id


async def test_submit_run_and_fetch_events_end_to_end(
    client, run_worker, line4_project_dict
):
    project_id = await _create_project(client, line4_project_dict)

    resp = await client.post(
        f"/v1/projects/{project_id}/runs", json={"until": 3600}
    )
    run = resp.json()
    assert run["status"] == "queued"

    await run_worker(run["id"])

    resp = await client.get(f"/v1/runs/{run['id']}")
    assert resp.status_code == 200
    completed = resp.json()
    assert completed["status"] == "completed"
    assert completed["sim_time_now"] == 3600

    resp = await client.get(f"/v1/runs/{run['id']}/events")
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) > 0
    assert {e["event"] for e in events} <= {"IN", "OUT", "LOC"}
    # Events come back in insertion (seq) order, which the worker assigns
    # in non-decreasing sim-time order - a basic ordering sanity check.
    assert [e["time"] for e in events] == sorted(e["time"] for e in events)


async def test_submit_run_for_missing_project_404s(client):
    resp = await client.post(
        "/v1/projects/00000000-0000-0000-0000-000000000000/runs", json={}
    )
    assert resp.status_code == 404


async def test_run_events_filtering(client, run_worker, line4_project_dict):
    project_id = await _create_project(client, line4_project_dict)
    resp = await client.post(
        f"/v1/projects/{project_id}/runs", json={"until": 3600}
    )
    run = resp.json()
    await run_worker(run["id"])

    resp = await client.get(
        f"/v1/runs/{run['id']}/events", params={"event_type": "IN"}
    )
    assert resp.status_code == 200
    assert all(e["event"] == "IN" for e in resp.json())

    resp = await client.get(f"/v1/runs/{run['id']}/events")
    all_events = resp.json()
    a_train = all_events[0]["train_uid"]
    resp = await client.get(
        f"/v1/runs/{run['id']}/events", params={"train_uid": a_train}
    )
    assert resp.status_code == 200
    assert all(e["train_uid"] == a_train for e in resp.json())


async def test_list_runs_filters_by_project(client, line4_project_dict):
    p1 = await _create_project(client, line4_project_dict)
    p2 = await _create_project(client, line4_project_dict)
    await client.post(f"/v1/projects/{p1}/runs", json={"until": 100})
    await client.post(f"/v1/projects/{p2}/runs", json={"until": 100})

    resp = await client.get("/v1/runs", params={"project_id": p1})
    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) == 1
    assert runs[0]["project_id"] == p1


async def test_cancel_stops_run_early(client, run_worker, line4_project_dict):
    project_id = await _create_project(client, line4_project_dict)
    # A long horizon and small chunk_size so there's a real window to
    # cancel inside before the run would otherwise finish.
    resp = await client.post(
        f"/v1/projects/{project_id}/runs",
        json={"until": 36900, "chunk_size": 60},
    )
    run = resp.json()

    resp = await client.post(f"/v1/runs/{run['id']}/cancel")
    assert resp.status_code == 200

    await run_worker(run["id"])

    resp = await client.get(f"/v1/runs/{run['id']}")
    body = resp.json()
    assert body["status"] == "cancelled"
    assert body["sim_time_now"] < 36900


async def _run_to_completion(client, run_worker, project_id, **body):
    resp = await client.post(f"/v1/projects/{project_id}/runs", json=body)
    assert resp.status_code == 202
    run = resp.json()
    await run_worker(run["id"])
    events = (await client.get(f"/v1/runs/{run['id']}/events?limit=10000")).json()
    return run, events


async def test_same_seed_gives_identical_events(client, run_worker, line4_project_dict):
    project_id = await _create_project(client, line4_project_dict)

    run_a, events_a = await _run_to_completion(
        client, run_worker, project_id, until=36900, seed=7
    )
    run_b, events_b = await _run_to_completion(
        client, run_worker, project_id, until=36900, seed=7
    )

    assert run_a["seed"] == run_b["seed"] == 7
    assert len(events_a) > 0
    assert events_a == events_b


async def test_different_seeds_give_different_events(
    client, run_worker, line4_project_dict
):
    project_id = await _create_project(client, line4_project_dict)

    _, events_a = await _run_to_completion(
        client, run_worker, project_id, until=36900, seed=7
    )
    _, events_b = await _run_to_completion(
        client, run_worker, project_id, until=36900, seed=8
    )

    assert events_a != events_b


async def test_omitted_seed_is_chosen_and_recorded_so_the_run_can_be_replayed(
    client, run_worker, line4_project_dict
):
    project_id = await _create_project(client, line4_project_dict)

    run, events = await _run_to_completion(
        client, run_worker, project_id, until=36900
    )
    assert isinstance(run["seed"], int) and run["seed"] >= 0

    # The recorded seed is visible on later reads too.
    fetched = (await client.get(f"/v1/runs/{run['id']}")).json()
    assert fetched["seed"] == run["seed"]

    # Resubmitting with that seed reproduces the run exactly.
    _, replay = await _run_to_completion(
        client, run_worker, project_id, until=36900, seed=run["seed"]
    )
    assert replay == events


async def test_omitted_seeds_differ_between_runs(client, line4_project_dict):
    project_id = await _create_project(client, line4_project_dict)
    seeds = set()
    for _ in range(3):
        resp = await client.post(f"/v1/projects/{project_id}/runs", json={})
        seeds.add(resp.json()["seed"])
    assert len(seeds) == 3


@pytest.mark.parametrize("bad_seed", [-1, 2**63, "abc", 1.5])
async def test_invalid_seed_is_rejected(client, line4_project_dict, bad_seed):
    project_id = await _create_project(client, line4_project_dict)
    resp = await client.post(
        f"/v1/projects/{project_id}/runs", json={"seed": bad_seed}
    )
    assert resp.status_code == 422


async def test_largest_allowed_seed_round_trips_through_the_database(
    client, line4_project_dict
):
    project_id = await _create_project(client, line4_project_dict)
    seed = 2**63 - 1
    resp = await client.post(f"/v1/projects/{project_id}/runs", json={"seed": seed})
    assert resp.status_code == 202
    assert resp.json()["seed"] == seed


async def test_until_target_is_the_requested_time(client, line4_project_dict):
    project_id = await _create_project(client, line4_project_dict)
    run = (
        await client.post(f"/v1/projects/{project_id}/runs", json={"until": 3600})
    ).json()
    assert run["requested_until"] == 3600
    assert run["until_target"] == 3600


async def test_until_target_is_derived_when_no_end_is_requested(
    client, run_worker, line4_project_dict
):
    project_id = await _create_project(client, line4_project_dict)
    expected = max(t["deletion_time"] for t in line4_project_dict["tours"])

    run = (await client.post(f"/v1/projects/{project_id}/runs", json={})).json()
    # Known immediately, while still queued, so a client can show 0 / target.
    assert run["status"] == "queued"
    assert run["requested_until"] is None
    assert run["until_target"] == expected

    await run_worker(run["id"])
    done = (await client.get(f"/v1/runs/{run['id']}")).json()
    assert done["status"] == "completed"
    assert done["sim_time_now"] == done["until_target"] == expected


async def test_runs_without_until_target_still_run(
    client, run_worker, line4_project_dict
):
    from uuid import UUID

    from sqlalchemy import update

    from spur_api.db.models import SimulationRunRow
    from spur_api.db.session import get_session_factory

    project_id = await _create_project(client, line4_project_dict)
    run = (
        await client.post(f"/v1/projects/{project_id}/runs", json={"until": 3600})
    ).json()
    async with get_session_factory()() as db:
        await db.execute(
            update(SimulationRunRow)
            .where(SimulationRunRow.id == UUID(run["id"]))
            .values(until_target=None)
        )
        await db.commit()

    await run_worker(run["id"])

    done = (await client.get(f"/v1/runs/{run['id']}")).json()
    assert done["status"] == "completed" and done["sim_time_now"] == 3600
    assert done["until_target"] is None
