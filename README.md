# spur-api

An HTTP API service wrapping [spur](https://github.com/spur-sim/spur), a mesoscopic railway
simulation engine, so it can be driven by anything that speaks HTTP rather than only
Python. MIT-licensed, like spur itself.

**Status: Phase 1 (skeleton).** The API runs simulations synchronously, in-process, with an
in-memory store — no database, no background worker, no streaming yet. Roadmap: Phase 2 adds
Postgres + a background job queue (arq/Redis) so runs don't block a request; Phase 3 adds
WebSocket/SSE progress streaming; Phase 4 adds a real auth backend and Docker packaging.

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn spur_api.main:app --reload
```

Then, in another terminal:

```bash
# Create a project (a spur "ProjectSpec" - components/routes/tours/trains)
curl -s -X POST http://127.0.0.1:8000/v1/projects \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/line4_project.json | tee /tmp/project.json

PROJECT_ID=$(python3 -c "import json; print(json.load(open('/tmp/project.json'))['id'])")

# Submit a run - runs synchronously in Phase 1, returns once complete
curl -s -X POST "http://127.0.0.1:8000/v1/projects/$PROJECT_ID/runs" \
  -H "Content-Type: application/json" \
  -d '{"until": 3600}' | tee /tmp/run.json

RUN_ID=$(python3 -c "import json; print(json.load(open('/tmp/run.json'))['id'])")

# Fetch structured events (IN/OUT/LOC) from the run
curl -s "http://127.0.0.1:8000/v1/runs/$RUN_ID/events?limit=10"
```

## Running tests

```bash
pytest
```

## Project shape

A "project" is exactly `spur.io.schema.ProjectSpec` (components/routes/tours/trains) plus
API-owned metadata (`id`, `owner`, timestamps) - see `spur_api/schemas/project.py`. This is
deliberately not a divergent resource model: anything valid for `spur.io.formats.read_project_json`
is valid here.

## Configuration

See `.env.example`. All settings are optional in Phase 1.
