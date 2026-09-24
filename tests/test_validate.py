import copy
import os

import pytest
import redis.asyncio as aioredis

from spur_api.config import settings


def _mutated(project, *mutations):
    p = copy.deepcopy(project)
    for m in mutations:
        m(p)
    return p


def _break_type(p):
    p["components"][0]["type"] = "Nope"


def _break_component_ref(p):
    p["routes"][0]["components"][3]["u"] = "nowhere"


def _break_route_ref(p):
    p["tours"][0]["routes"][1]["name"] = "R-Sideways"


def _break_tour_ref(p):
    p["trains"][0]["tour"] = "Tour-999"


def _warning_only(p):
    p["tours"][0]["creation_time"] = p["tours"][0]["deletion_time"]


async def _validate(client, body):
    resp = await client.post("/v1/validate", json=body)
    assert resp.status_code == 200
    return resp.json()


def _paths(result, severity=None):
    return {i["path"] for i in result["issues"] if severity in (None, i["severity"])}


@pytest.fixture
def auth_on(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "api_keys", ["good-key"])


class TestValidateEndpoint:
    async def test_a_clean_project(self, client, line4_project_dict):
        assert await _validate(client, line4_project_dict) == {"valid": True, "issues": []}

    async def test_every_problem_is_reported_together(self, client, line4_project_dict):
        broken = _mutated(
            line4_project_dict,
            _break_type, _break_component_ref, _break_route_ref, _break_tour_ref,
        )
        result = await _validate(client, broken)
        assert result["valid"] is False
        assert _paths(result, "error") >= {
            "components[0].type",
            "routes[0].components[3]",
            "tours[0].routes[1].name",
            "trains[0].tour",
        }
        assert all({"severity", "path", "message"} == set(i) for i in result["issues"])

    async def test_a_warning_does_not_make_a_project_invalid(
        self, client, line4_project_dict
    ):
        result = await _validate(client, _mutated(line4_project_dict, _warning_only))
        assert result["valid"] is True
        assert [(i["severity"], i["path"]) for i in result["issues"]] == [
            ("warning", "tours[0].deletion_time")
        ]

    @pytest.mark.parametrize(
        "field,path", [("type", "type"), ("spur_version", "spur_version")]
    )
    async def test_missing_envelope_fields(
        self, client, line4_project_dict, field, path
    ):
        draft = _mutated(line4_project_dict, lambda p: p.pop(field))
        result = await _validate(client, draft)
        assert result["valid"] is False and path in _paths(result, "error")

    async def test_wrong_project_type(self, client, line4_project_dict):
        draft = _mutated(line4_project_dict, lambda p: p.update(type="Other"))
        assert "type" in _paths(await _validate(client, draft), "error")

    async def test_envelope_and_structural_problems_come_together(
        self, client, line4_project_dict
    ):
        draft = _mutated(line4_project_dict, lambda p: p.pop("type"), _break_type)
        assert _paths(await _validate(client, draft), "error") >= {
            "type", "components[0].type",
        }

    async def test_schema_errors_use_the_same_format(self, client, line4_project_dict):
        draft = _mutated(line4_project_dict, lambda p: p["components"][0].pop("u"))
        result = await _validate(client, draft)
        assert "components[0].u" in _paths(result, "error")

    @pytest.mark.parametrize("raw", ["[]", '"project"', "3", "null"])
    async def test_a_body_that_is_not_an_object(self, client, raw):
        resp = await client.post(
            "/v1/validate", content=raw, headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["valid"] is False and result["issues"][0]["path"] == ""

    async def test_no_body_at_all(self, client):
        resp = await client.post("/v1/validate")
        assert resp.status_code == 200 and resp.json()["valid"] is False

    async def test_a_body_that_is_not_json(self, client):
        resp = await client.post(
            "/v1/validate", content="{not json", headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 422

    async def test_it_saves_nothing(self, client, line4_project_dict):
        await _validate(client, line4_project_dict)
        assert (await client.get("/v1/projects")).json() == []

    async def test_it_needs_an_api_key_when_auth_is_on(
        self, auth_on, client, line4_project_dict
    ):
        assert (await client.post("/v1/validate", json=line4_project_dict)).status_code == 401
        resp = await client.post(
            "/v1/validate",
            json=line4_project_dict,
            headers={"Authorization": "Bearer good-key"},
        )
        assert resp.status_code == 200 and resp.json()["valid"] is True


class TestAgreementWithSaving:
    """`valid` means POST /v1/projects would accept it *and* it is structurally
    sound. Saving is permissive, so drafts with structural errors still save."""

    async def test_a_valid_project_saves(self, client, line4_project_dict):
        assert (await _validate(client, line4_project_dict))["valid"] is True
        assert (await client.post("/v1/projects", json=line4_project_dict)).status_code == 201

    @pytest.mark.parametrize(
        "mutation",
        [lambda p: p.pop("trains"), lambda p: p.pop("type"), lambda p: p.pop("spur_version"),
         lambda p: p["components"][0].pop("u")],
        ids=["missing section", "missing type", "missing version", "bad component"],
    )
    async def test_what_saving_rejects_is_never_valid(
        self, client, line4_project_dict, mutation
    ):
        draft = _mutated(line4_project_dict, mutation)
        assert (await _validate(client, draft))["valid"] is False
        assert (await client.post("/v1/projects", json=draft)).status_code == 422

    @pytest.mark.parametrize(
        "mutation",
        [_break_type, _break_component_ref, _break_route_ref, _break_tour_ref],
        ids=["type", "component ref", "route ref", "tour ref"],
    )
    async def test_structural_errors_are_invalid_but_still_save_as_drafts(
        self, client, line4_project_dict, mutation
    ):
        draft = _mutated(line4_project_dict, mutation)
        assert (await _validate(client, draft))["valid"] is False
        assert (await client.post("/v1/projects", json=draft)).status_code == 201


class TestRunSubmissionGate:
    @staticmethod
    async def _save(client, project):
        resp = await client.post("/v1/projects", json=project)
        assert resp.status_code == 201
        return resp.json()["id"]

    async def test_a_broken_project_is_rejected_before_a_run_exists(
        self, client, line4_project_dict
    ):
        project_id = await self._save(
            client, _mutated(line4_project_dict, _break_route_ref, _break_tour_ref)
        )

        resp = await client.post(f"/v1/projects/{project_id}/runs", json={"until": 3600})

        assert resp.status_code == 422
        body = resp.json()
        assert "2 error(s)" in body["detail"]
        assert {i["path"] for i in body["issues"]} >= {
            "tours[0].routes[1].name", "trains[0].tour",
        }
        assert (await client.get("/v1/runs")).json() == []
        # Nothing was queued either.
        r = aioredis.from_url(os.environ["SPUR_API_REDIS_URL"])
        try:
            assert await r.keys("arq:*") == []
        finally:
            await r.aclose()

    async def test_issues_include_warnings_alongside_errors(
        self, client, line4_project_dict
    ):
        project_id = await self._save(
            client, _mutated(line4_project_dict, _break_tour_ref, _warning_only)
        )
        resp = await client.post(f"/v1/projects/{project_id}/runs", json={})
        assert {i["severity"] for i in resp.json()["issues"]} == {"error", "warning"}

    async def test_warnings_do_not_block_a_run(self, client, line4_project_dict):
        project_id = await self._save(
            client, _mutated(line4_project_dict, _warning_only)
        )
        resp = await client.post(f"/v1/projects/{project_id}/runs", json={"until": 3600})
        assert resp.status_code == 202 and resp.json()["status"] == "queued"

    async def test_fixing_the_project_lets_it_run(self, client, line4_project_dict):
        project_id = await self._save(
            client, _mutated(line4_project_dict, _break_type)
        )
        assert (await client.post(f"/v1/projects/{project_id}/runs", json={})).status_code == 422

        await client.put(f"/v1/projects/{project_id}", json=line4_project_dict)

        resp = await client.post(f"/v1/projects/{project_id}/runs", json={"until": 3600})
        assert resp.status_code == 202

    async def test_a_missing_project_is_still_a_404(self, client):
        resp = await client.post(
            "/v1/projects/00000000-0000-0000-0000-000000000000/runs", json={}
        )
        assert resp.status_code == 404
