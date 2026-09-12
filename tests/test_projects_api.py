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
