import re

import pytest

from spur_api.auth import key_fingerprint
from spur_api.config import settings
from spur_api.main import create_app


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


OPEN_ROUTES = {"/healthz", "/readyz"}


def _api_routes():
    """Every (method, path) the app serves, with path parameters filled in.
    Read from the app's own OpenAPI schema, so a new route can't be left out."""
    rid = "00000000-0000-0000-0000-000000000000"
    calls = []
    for path, operations in create_app().openapi()["paths"].items():
        if path in OPEN_ROUTES:
            continue
        for method in operations:
            calls.append((method.upper(), re.sub(r"\{[^}]+\}", rid, path)))
    return calls


def test_the_route_enumeration_is_not_vacuous():
    calls = _api_routes()
    assert len(calls) >= 15
    for expected in [
        ("POST", "/v1/validate"),
        ("GET", "/v1/catalog"),
        ("GET", "/v1/runs/00000000-0000-0000-0000-000000000000/summary"),
    ]:
        assert expected in calls


@pytest.mark.parametrize("method,path", _api_routes())
async def test_every_non_health_route_requires_auth(client, auth_on, method, path):
    resp = await client.request(method, path)
    assert resp.status_code == 401, f"{method} {path} is not protected"


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
