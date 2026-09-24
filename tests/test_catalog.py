import pytest

from spur.catalog import catalog as spur_catalog

from spur_api.config import settings


@pytest.fixture
def auth_on(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "api_keys", ["good-key"])


async def _get(client):
    resp = await client.get("/v1/catalog")
    assert resp.status_code == 200
    return resp.json()


def _type(catalog, group, name):
    return next(t for t in catalog[group] if t["name"] == name)


async def test_it_is_spurs_catalog(client):
    assert await _get(client) == spur_catalog().model_dump(mode="json")


async def test_shape(client):
    catalog = await _get(client)
    assert set(catalog) == {"components", "jitters", "collections"}

    track = _type(catalog, "components", "TimedTrack")
    assert set(track) == {"name", "summary", "parameters"}
    assert track["parameters"][0] == {
        "name": "traversal_time",
        "type": "integer",
        "required": True,
        "default": None,
        "description": track["parameters"][0]["description"],
    }
    assert track["parameters"][0]["description"]
    capacity = track["parameters"][1]
    assert (capacity["name"], capacity["required"], capacity["default"]) == ("capacity", False, 1)


async def test_lists_every_kind_of_type(client):
    catalog = await _get(client)
    # DynamicDwellStation was usable in code but unreachable from a project until
    # spur derived its type list from the classes.
    assert {"TimedTrack", "SimpleStation", "DynamicDwellStation"} <= {
        t["name"] for t in catalog["components"]
    }
    assert {"NoJitter", "DisruptionJitter"} <= {t["name"] for t in catalog["jitters"]}
    assert [t["name"] for t in catalog["collections"]] == ["BlockExclusiveZone"]


async def test_it_needs_an_api_key_when_auth_is_on(auth_on, client):
    assert (await client.get("/v1/catalog")).status_code == 401
    resp = await client.get("/v1/catalog", headers={"Authorization": "Bearer good-key"})
    assert resp.status_code == 200


async def test_it_is_in_the_openapi_spec(client):
    spec = (await client.get("/openapi.json")).json()
    assert "/v1/catalog" in spec["paths"]


def _sample(parameter):
    if not parameter["required"]:
        return parameter["default"]
    return {"integer": 2, "number": 0.5, "string": "x", "boolean": True}[parameter["type"]]


def _args(type_info):
    return {p["name"]: _sample(p) for p in type_info["parameters"]}


async def test_an_editor_can_build_valid_projects_from_it(client):
    """Use nothing but what the endpoint returns, the way an editor would, and
    ask the validate endpoint whether the result is acceptable."""
    catalog = await _get(client)
    envelope = {"type": "SpurProject", "spur_version": "v1.0.0", "routes": [], "tours": [], "trains": []}
    track = _type(catalog, "components", "TimedTrack")

    def component(type_info, **extra):
        return {"type": type_info["name"], "u": "a", "v": "b", "key": "K", "args": _args(type_info), **extra}

    projects = {}
    for t in catalog["components"]:
        projects[f"component {t['name']}"] = [component(t)]
    for t in catalog["jitters"]:
        projects[f"jitter {t['name']}"] = [
            component(track, jitter={"type": t["name"], "args": _args(t)})
        ]
    for t in catalog["collections"]:
        projects[f"collection {t['name']}"] = [
            component(track, collection={"type": t["name"], "key": "zone"})
        ]

    assert len(projects) == 8 + 5 + 1
    for label, components in projects.items():
        resp = await client.post("/v1/validate", json={**envelope, "components": components})
        assert resp.json() == {"valid": True, "issues": []}, label
