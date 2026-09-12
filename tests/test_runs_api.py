def _create_project(client, line4_project_dict):
    resp = client.post("/v1/projects", json=line4_project_dict)
    assert resp.status_code == 201
    return resp.json()["id"]


def test_submit_run_and_fetch_events_end_to_end(client, line4_project_dict):
    project_id = _create_project(client, line4_project_dict)

    resp = client.post(f"/v1/projects/{project_id}/runs", json={"until": 3600})
    assert resp.status_code == 201
    run = resp.json()
    assert run["status"] == "completed"
    assert run["sim_time_now"] == 3600

    resp = client.get(f"/v1/runs/{run['id']}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"

    resp = client.get(f"/v1/runs/{run['id']}/events")
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) > 0
    assert {e["event"] for e in events} <= {"IN", "OUT", "LOC"}


def test_submit_run_for_missing_project_404s(client):
    resp = client.post(
        "/v1/projects/00000000-0000-0000-0000-000000000000/runs", json={}
    )
    assert resp.status_code == 404


def test_run_events_filtering(client, line4_project_dict):
    project_id = _create_project(client, line4_project_dict)
    run = client.post(
        f"/v1/projects/{project_id}/runs", json={"until": 3600}
    ).json()

    resp = client.get(f"/v1/runs/{run['id']}/events", params={"event_type": "IN"})
    assert resp.status_code == 200
    assert all(e["event"] == "IN" for e in resp.json())

    all_events = client.get(f"/v1/runs/{run['id']}/events").json()
    a_train = all_events[0]["train_uid"]
    resp = client.get(
        f"/v1/runs/{run['id']}/events", params={"train_uid": a_train}
    )
    assert resp.status_code == 200
    assert all(e["train_uid"] == a_train for e in resp.json())


def test_list_runs_filters_by_project(client, line4_project_dict):
    p1 = _create_project(client, line4_project_dict)
    p2 = _create_project(client, line4_project_dict)
    client.post(f"/v1/projects/{p1}/runs", json={"until": 100})
    client.post(f"/v1/projects/{p2}/runs", json={"until": 100})

    resp = client.get("/v1/runs", params={"project_id": p1})
    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) == 1
    assert runs[0]["project_id"] == p1
