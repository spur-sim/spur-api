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
