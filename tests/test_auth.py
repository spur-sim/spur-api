import pytest

from spur_api.auth import key_fingerprint
from spur_api.config import settings


@pytest.fixture
def auth_on(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "api_keys", ["good-key"])


async def test_auth_disabled_by_default_allows_requests(client):
    resp = await client.get("/v1/projects")
    assert resp.status_code == 200


async def test_missing_header_is_rejected(client, auth_on):
    resp = await client.get("/v1/projects")
    assert resp.status_code == 401


async def test_wrong_key_is_rejected(client, auth_on):
    resp = await client.get(
        "/v1/projects", headers={"Authorization": "Bearer nope"}
    )
    assert resp.status_code == 401


async def test_valid_key_is_accepted(client, auth_on):
    resp = await client.get(
        "/v1/projects", headers={"Authorization": "Bearer good-key"}
    )
    assert resp.status_code == 200


async def test_every_non_health_route_requires_auth(client, auth_on):
    rid = "00000000-0000-0000-0000-000000000000"
    calls = [
        ("get", "/v1/projects"),
        ("post", "/v1/projects"),
        ("get", f"/v1/projects/{rid}"),
        ("put", f"/v1/projects/{rid}"),
        ("delete", f"/v1/projects/{rid}"),
        ("post", f"/v1/projects/{rid}/runs"),
        ("get", "/v1/runs"),
        ("get", f"/v1/runs/{rid}"),
        ("post", f"/v1/runs/{rid}/cancel"),
        ("delete", f"/v1/runs/{rid}"),
        ("get", f"/v1/runs/{rid}/events"),
    ]
    for method, path in calls:
        resp = await getattr(client, method)(path)
        assert resp.status_code == 401, f"{method.upper()} {path} not protected"


async def test_health_endpoints_stay_open(client, auth_on):
    assert (await client.get("/healthz")).status_code == 200
    assert (await client.get("/readyz")).status_code == 200


async def test_project_owner_is_the_api_key_principal(
    client, auth_on, line4_project_dict
):
    resp = await client.post(
        "/v1/projects",
        json=line4_project_dict,
        headers={"Authorization": "Bearer good-key"},
    )
    assert resp.status_code == 201
    assert resp.json()["owner"] == key_fingerprint("good-key")
    assert "good-key" not in resp.text
