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


async def test_extensions_are_kept_exactly_as_given(client, line4_project_dict):
    # Data a tool keeps with a project (spur's `extensions` section). The API
    # stores and returns it without looking inside.
    extensions = {
        "ui": {"version": 1, "nodes": [{"id": "yonge-east", "lonlat": [-79.41, 43.76]}]},
        "other-tool": {"anything": None},
    }
    resp = await client.post(
        "/v1/projects", json=dict(line4_project_dict, extensions=extensions)
    )
    assert resp.status_code == 201
    created = resp.json()
    assert created["extensions"] == extensions

    resp = await client.get(f"/v1/projects/{created['id']}")
    assert resp.json()["extensions"] == extensions

    moved = {"ui": {"version": 1, "nodes": []}}
    resp = await client.put(
        f"/v1/projects/{created['id']}", json=dict(line4_project_dict, extensions=moved)
    )
    assert resp.status_code == 200
    assert resp.json()["extensions"] == moved


async def test_extensions_must_be_an_object(client, line4_project_dict):
    resp = await client.post(
        "/v1/projects", json=dict(line4_project_dict, extensions=["not", "an", "object"])
    )
    assert resp.status_code == 422


async def test_a_project_with_extensions_still_runs(client, line4_project_dict):
    project = dict(line4_project_dict, extensions={"ui": {"nodes": "any shape at all"}})
    created = (await client.post("/v1/projects", json=project)).json()

    resp = await client.post(f"/v1/projects/{created['id']}/runs", json={"until": 100})
    assert resp.status_code == 202


async def test_each_save_raises_the_version(client, line4_project_dict):
    created = (await client.post("/v1/projects", json=line4_project_dict)).json()
    assert created["version"] == 1

    saved = await client.put(f"/v1/projects/{created['id']}", json=line4_project_dict)
    assert saved.json()["version"] == 2
    assert (await client.get(f"/v1/projects/{created['id']}")).json()["version"] == 2


async def test_a_save_from_a_stale_copy_is_refused(client, line4_project_dict):
    project_id = (await client.post("/v1/projects", json=line4_project_dict)).json()["id"]
    url = f"/v1/projects/{project_id}"
    mine = {**line4_project_dict, "name": "Mine"}
    theirs = {**line4_project_dict, "name": "Theirs"}

    # Two tabs load version 1. The first to save wins.
    first = await client.put(url, json=theirs, headers={"If-Match": "1"})
    assert first.status_code == 200
    second = await client.put(url, json=mine, headers={"If-Match": "1"})

    assert second.status_code == 412
    # The refusal says where the project is now, and nothing was overwritten.
    assert second.json()["version"] == 2
    assert (await client.get(url)).json()["name"] == "Theirs"

    # Saving again from the current version goes through.
    retry = await client.put(url, json=mine, headers={"If-Match": "2"})
    assert retry.status_code == 200
    assert retry.json()["version"] == 3


async def test_if_match_may_be_quoted_and_must_be_a_version(client, line4_project_dict):
    project_id = (await client.post("/v1/projects", json=line4_project_dict)).json()["id"]
    url = f"/v1/projects/{project_id}"

    quoted = await client.put(url, json=line4_project_dict, headers={"If-Match": '"1"'})
    assert quoted.status_code == 200

    nonsense = await client.put(url, json=line4_project_dict, headers={"If-Match": "latest"})
    assert nonsense.status_code == 400
