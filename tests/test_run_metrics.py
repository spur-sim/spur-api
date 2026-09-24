from uuid import UUID

import pytest
from sqlalchemy import update

from spur_api.db.models import SimulationRunRow
from spur_api.db.session import get_session_factory

UNTIL = 36900  # a full service day; trains are idle in the yards before ~20850
MISSING = "00000000-0000-0000-0000-000000000000"


async def _project(client, project_dict):
    resp = await client.post("/v1/projects", json=project_dict)
    assert resp.status_code == 201
    return resp.json()["id"]


async def _submit(client, project_id, **body):
    resp = await client.post(f"/v1/projects/{project_id}/runs", json=body)
    assert resp.status_code == 202
    return resp.json()


async def _completed_run(client, run_worker, project_id, **body):
    run = await _submit(client, project_id, **{"until": UNTIL, "seed": 1, **body})
    await run_worker(run["id"])
    return run


async def _events(client, run_id):
    resp = await client.get(f"/v1/runs/{run_id}/events", params={"limit": 10000})
    return resp.json()


async def test_summary_of_a_completed_run(client, run_worker, line4_project_dict):
    project_id = await _project(client, line4_project_dict)
    run = await _completed_run(client, run_worker, project_id)

    resp = await client.get(f"/v1/runs/{run['id']}/summary")
    assert resp.status_code == 200
    s = resp.json()

    assert s["status"] == "completed"
    assert s["run"]["events"] == len(await _events(client, run["id"]))
    assert s["run"]["on_time_threshold"] == 120
    assert s["components"] and len(s["trains"]) == 4
    assert sum(c["visits"] for c in s["components"]) == s["run"]["visits"]
    assert sum(t["visits"] for t in s["trains"]) == s["run"]["visits"]
    # Trains are held to schedule, so nobody leaves early.
    assert s["run"]["departure_delay"]["n"] > 0
    assert s["run"]["departure_delay"]["min"] >= 0
    stations = [c for c in s["components"] if c["component_type"] == "SimpleStation"]
    assert stations and all(c["occupancy"]["mean"] > 0 for c in stations)


async def test_on_time_threshold_changes_on_time_pct(
    client, run_worker, line4_project_dict
):
    project_id = await _project(client, line4_project_dict)
    run = await _completed_run(client, run_worker, project_id)

    async def pct(threshold):
        resp = await client.get(
            f"/v1/runs/{run['id']}/summary", params={"on_time_threshold": threshold}
        )
        assert resp.json()["run"]["on_time_threshold"] == threshold
        return resp.json()["run"]["on_time_pct"]

    strict, default, lax = await pct(0), await pct(120), await pct(10**9)
    assert strict <= default <= lax
    assert lax == 100.0


async def test_negative_threshold_is_rejected(client, run_worker, line4_project_dict):
    project_id = await _project(client, line4_project_dict)
    run = await _completed_run(client, run_worker, project_id)
    resp = await client.get(
        f"/v1/runs/{run['id']}/summary", params={"on_time_threshold": -1}
    )
    assert resp.status_code == 422


async def test_same_seed_gives_identical_summaries(
    client, run_worker, line4_project_dict
):
    project_id = await _project(client, line4_project_dict)
    a = await _completed_run(client, run_worker, project_id, seed=9)
    b = await _completed_run(client, run_worker, project_id, seed=9)
    sa = (await client.get(f"/v1/runs/{a['id']}/summary")).json()
    sb = (await client.get(f"/v1/runs/{b['id']}/summary")).json()
    assert sa == sb


async def test_visits_are_filterable_and_pageable(
    client, run_worker, line4_project_dict
):
    project_id = await _project(client, line4_project_dict)
    run = await _completed_run(client, run_worker, project_id)
    summary = (await client.get(f"/v1/runs/{run['id']}/summary")).json()
    url = f"/v1/runs/{run['id']}/visits"

    everything = (await client.get(url, params={"limit": 10000})).json()
    assert len(everything) == summary["run"]["visits"]
    assert everything[0].keys() >= {
        "train_uid", "component_uid", "time_in", "time_out", "occupancy",
        "scheduled_departure", "departure_delay",
    }

    one_train = (await client.get(url, params={"train_uid": "T-0", "limit": 10000})).json()
    assert one_train and {v["train_uid"] for v in one_train} == {"T-0"}
    assert len(one_train) == next(t for t in summary["trains"] if t["train_uid"] == "T-0")["visits"]

    component = everything[0]["component_uid"]
    one_component = (
        await client.get(url, params={"component_uid": component, "limit": 10000})
    ).json()
    assert {v["component_uid"] for v in one_component} == {component}

    first = (await client.get(url, params={"limit": 5})).json()
    second = (await client.get(url, params={"limit": 5, "offset": 5})).json()
    assert first == everything[:5] and second == everything[5:10]


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 10001}, {"offset": -1}])
async def test_visits_paging_bounds(client, run_worker, line4_project_dict, params):
    project_id = await _project(client, line4_project_dict)
    run = await _completed_run(client, run_worker, project_id, until=100)
    resp = await client.get(f"/v1/runs/{run['id']}/visits", params=params)
    assert resp.status_code == 422


@pytest.mark.parametrize("path", ["summary", "visits"])
async def test_unknown_run_is_404(client, path):
    assert (await client.get(f"/v1/runs/{MISSING}/{path}")).status_code == 404


@pytest.mark.parametrize("path", ["summary", "visits"])
async def test_queued_run_is_409(client, line4_project_dict, path):
    project_id = await _project(client, line4_project_dict)
    run = await _submit(client, project_id, until=UNTIL)
    resp = await client.get(f"/v1/runs/{run['id']}/{path}")
    assert resp.status_code == 409
    assert "queued" in resp.json()["detail"]


async def test_cancelled_run_reports_what_it_has(
    client, run_worker, line4_project_dict
):
    project_id = await _project(client, line4_project_dict)
    run = await _submit(client, project_id, until=UNTIL, chunk_size=60)
    await client.post(f"/v1/runs/{run['id']}/cancel")
    await run_worker(run["id"])

    resp = await client.get(f"/v1/runs/{run['id']}/summary")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    assert resp.json()["run"]["visits"] == 0


class TestSpecSnapshot:
    """A run is analysed against the project it ran, not the project as edited since."""

    @staticmethod
    async def _submit_two_then_edit(client, project_id, project_dict):
        a = await _submit(client, project_id, until=UNTIL, seed=5)
        b = await _submit(client, project_id, until=UNTIL, seed=5)
        edited = await client.put(
            f"/v1/projects/{project_id}", json={**project_dict, "trains": []}
        )
        assert edited.status_code == 200
        return a, b

    async def test_queued_runs_ignore_a_later_edit(
        self, client, run_worker, line4_project_dict
    ):
        project_id = await _project(client, line4_project_dict)
        a, b = await self._submit_two_then_edit(client, project_id, line4_project_dict)

        await run_worker(a["id"])
        await run_worker(b["id"])

        events_a, events_b = await _events(client, a["id"]), await _events(client, b["id"])
        # The edited project has no trains; a run that saw it would be empty.
        assert len(events_a) > 0
        assert events_a == events_b

    async def test_analysis_uses_the_snapshot(
        self, client, run_worker, line4_project_dict
    ):
        project_id = await _project(client, line4_project_dict)
        a, _ = await self._submit_two_then_edit(client, project_id, line4_project_dict)
        await run_worker(a["id"])

        # Against the edited project this would be a mismatch (its trains are gone).
        resp = await client.get(f"/v1/runs/{a['id']}/summary")
        assert resp.status_code == 200
        assert len(resp.json()["trains"]) == 4
        assert resp.json()["run"]["visits"] > 0

    async def test_runs_submitted_after_the_edit_see_the_new_spec(
        self, client, run_worker, line4_project_dict
    ):
        project_id = await _project(client, line4_project_dict)
        await client.put(
            f"/v1/projects/{project_id}", json={**line4_project_dict, "trains": []}
        )
        run = await _completed_run(client, run_worker, project_id)

        assert await _events(client, run["id"]) == []
        resp = await client.get(f"/v1/runs/{run['id']}/summary")
        assert resp.status_code == 200 and resp.json()["trains"] == []

    async def test_runs_without_a_snapshot_fall_back_to_the_project(
        self, client, run_worker, line4_project_dict
    ):
        project_id = await _project(client, line4_project_dict)
        run = await _submit(client, project_id, until=UNTIL, seed=5)
        async with get_session_factory()() as db:
            await db.execute(
                update(SimulationRunRow)
                .where(SimulationRunRow.id == UUID(run["id"]))
                .values(spec_snapshot=None)
            )
            await db.commit()

        await run_worker(run["id"])

        assert len(await _events(client, run["id"])) > 0
        resp = await client.get(f"/v1/runs/{run['id']}/summary")
        assert resp.status_code == 200 and resp.json()["run"]["visits"] > 0

    async def test_events_that_do_not_match_the_project_are_a_422(
        self, client, run_worker, line4_project_dict
    ):
        project_id = await _project(client, line4_project_dict)
        run = await _completed_run(client, run_worker, project_id)
        # Corrupt the snapshot so it no longer describes what ran.
        async with get_session_factory()() as db:
            await db.execute(
                update(SimulationRunRow)
                .where(SimulationRunRow.id == UUID(run["id"]))
                .values(spec_snapshot={**line4_project_dict, "trains": []})
            )
            await db.commit()

        resp = await client.get(f"/v1/runs/{run['id']}/summary")
        assert resp.status_code == 422
        assert "do not match its project" in resp.json()["detail"]
