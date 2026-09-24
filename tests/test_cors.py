import pytest

from spur_api.config import settings

ORIGIN = "https://app.example.com"
PREFLIGHT = {
    "Origin": ORIGIN,
    "Access-Control-Request-Method": "POST",
    "Access-Control-Request-Headers": "authorization,content-type",
}


# `cors_on` must be requested before `client`: the middleware is added when
# the app is created, so the setting has to be in place by then.
@pytest.fixture
def cors_on(monkeypatch):
    monkeypatch.setattr(settings, "cors_origins", [ORIGIN])


@pytest.fixture
def auth_on(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "api_keys", ["good-key"])


async def test_cors_is_off_by_default(client):
    resp = await client.get("/healthz", headers={"Origin": ORIGIN})
    assert "access-control-allow-origin" not in resp.headers


async def test_allowed_origin_gets_the_header(cors_on, client):
    resp = await client.get("/healthz", headers={"Origin": ORIGIN})
    assert resp.headers["access-control-allow-origin"] == ORIGIN


async def test_preflight_is_answered(cors_on, client):
    resp = await client.options("/v1/projects", headers=PREFLIGHT)
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == ORIGIN
    assert "authorization" in resp.headers["access-control-allow-headers"].lower()
    assert "POST" in resp.headers["access-control-allow-methods"]


async def test_preflight_needs_no_api_key(cors_on, auth_on, client):
    # Browsers never send credentials on a preflight, so it must not hit auth.
    resp = await client.options("/v1/projects", headers=PREFLIGHT)
    assert resp.status_code == 200


async def test_disallowed_origin_is_refused(cors_on, client):
    headers = {**PREFLIGHT, "Origin": "https://evil.example.com"}
    resp = await client.options("/v1/projects", headers=headers)
    assert resp.status_code == 400
    assert "access-control-allow-origin" not in resp.headers

    resp = await client.get("/healthz", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in resp.headers


async def test_authenticated_request_from_the_allowed_origin(cors_on, auth_on, client):
    resp = await client.get(
        "/v1/projects", headers={"Origin": ORIGIN, "Authorization": "Bearer good-key"}
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == ORIGIN


async def test_error_responses_carry_the_header_so_the_browser_can_read_them(
    cors_on, auth_on, client
):
    resp = await client.get("/v1/projects", headers={"Origin": ORIGIN})
    assert resp.status_code == 401
    assert resp.headers["access-control-allow-origin"] == ORIGIN
