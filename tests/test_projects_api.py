import pytest


async def test_create_and_get_project(client, line4_project_dict):
    resp = await client.post("/v1/projects", json=line4_project_dict)
    assert resp.status_code == 201
    created = resp.json()
    assert created["name"] == line4_project_dict["name"]
    assert "id" in created

    resp = await client.get(f"/v1/projects/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


async def test_get_missing_project_404s(client):
    resp = await client.get("/v1/projects/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


async def test_list_projects(client, line4_project_dict):
    await client.post("/v1/projects", json=line4_project_dict)
    await client.post("/v1/projects", json=line4_project_dict)
    resp = await client.get("/v1/projects")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


async def test_create_project_rejects_invalid_spec(client):
    resp = await client.post("/v1/projects", json={"type": "SpurProject"})
    assert resp.status_code == 422


async def test_update_and_delete_project(client, line4_project_dict):
    resp = await client.post("/v1/projects", json=line4_project_dict)
    created = resp.json()

    renamed = dict(line4_project_dict, name="Renamed")
    resp = await client.put(f"/v1/projects/{created['id']}", json=renamed)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed"

    resp = await client.delete(f"/v1/projects/{created['id']}")
    assert resp.status_code == 204
    resp = await client.get(f"/v1/projects/{created['id']}")
    assert resp.status_code == 404


async def test_list_returns_summaries_without_the_spec(client, line4_project_dict):
    await client.post("/v1/projects", json=line4_project_dict)
    resp = await client.get("/v1/projects")
    assert resp.status_code == 200
    (item,) = resp.json()

    assert set(item) == {
        "id", "name", "spur_version", "owner", "created_at", "updated_at", "counts",
    }
    assert item["name"] == line4_project_dict["name"]
    assert item["counts"] == {
        k: len(line4_project_dict[k]) for k in ("components", "routes", "tours", "trains")
    }
    # The full spec is ~80 KB; a list of these should be tiny.
    assert len(resp.content) < 1000


async def test_list_is_newest_first_and_pageable(client, line4_project_dict):
    for name in ("first", "second", "third"):
        await client.post("/v1/projects", json={**line4_project_dict, "name": name})

    names = [p["name"] for p in (await client.get("/v1/projects")).json()]
    assert names == ["third", "second", "first"]

    page = (await client.get("/v1/projects", params={"limit": 2, "offset": 1})).json()
    assert [p["name"] for p in page] == ["second", "first"]


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 1001}, {"offset": -1}])
async def test_list_paging_bounds(client, params):
    resp = await client.get("/v1/projects", params=params)
    assert resp.status_code == 422


async def test_summary_counts_reflect_an_update(client, line4_project_dict):
    created = (await client.post("/v1/projects", json=line4_project_dict)).json()
    await client.put(
        f"/v1/projects/{created['id']}", json={**line4_project_dict, "trains": []}
    )
    (item,) = (await client.get("/v1/projects")).json()
    assert item["counts"]["trains"] == 0
    assert item["counts"]["components"] == len(line4_project_dict["components"])
