# spur-api

An HTTP API service wrapping [spur](https://github.com/spur-sim/spur), a mesoscopic railway
simulation engine, so it can be driven by anything that speaks HTTP rather than only
Python. MIT-licensed, like spur itself.

**Status: prototype.** Simulation runs execute in a background worker (arq/Redis), with
Postgres persisting projects, runs, and structured events. Submitting a run returns
immediately with `status=queued`; poll `GET /v1/runs/{id}` until it reaches `completed`,
`failed`, or `cancelled`, then read the events.

**Known limitations**
- **Polling only.** No WebSocket/SSE streaming yet. Deferred until polling latency is a
  real problem; the data already lives in Postgres, so streaming can be added without
  changing the existing endpoints.
- **spur is installed from its `main` branch**, not a released version, so a new spur
  commit can change behaviour under this service. Pin to a release once spur publishes one.
- **Single tenant.** Auth is a static API-key check (below), with no users, orgs, or roles.

## Quickstart (Docker)

```bash
docker compose up --build
```

This starts Postgres, Redis, the API (`localhost:8000`, running migrations on startup), and
a worker. Then, in another terminal:

```bash
# Create a project (a spur "ProjectSpec" - components/routes/tours/trains)
curl -s -X POST http://127.0.0.1:8000/v1/projects \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/line4_project.json | tee /tmp/project.json

PROJECT_ID=$(python3 -c "import json; print(json.load(open('/tmp/project.json'))['id'])")

# Submit a run - returns immediately with status=queued; a worker picks it up
curl -s -X POST "http://127.0.0.1:8000/v1/projects/$PROJECT_ID/runs" \
  -H "Content-Type: application/json" \
  -d '{"until": 3600}' | tee /tmp/run.json

RUN_ID=$(python3 -c "import json; print(json.load(open('/tmp/run.json'))['id'])")

# Poll until it's done
curl -s "http://127.0.0.1:8000/v1/runs/$RUN_ID"

# Fetch structured events (IN/OUT/LOC) from the run
curl -s "http://127.0.0.1:8000/v1/runs/$RUN_ID/events?limit=10"
```

## Quickstart (local, without Docker)

Requires a running Postgres and Redis (see `.env.example` for the expected connection
strings, or run just those two services via `docker compose up postgres redis`).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn spur_api.main:app --reload &
arq spur_api.worker.settings.WorkerSettings &
```

Then follow the same curl walkthrough as above.

## Running tests

Tests need a real Postgres and Redis too (see `tests/conftest.py` for the expected
connection strings - defaults assume dev instances on ports 5433/6380 to avoid colliding
with anything already running on the standard ports). Then:

```bash
pytest
```

## Reproducible runs

Runs use random jitter, so by default two runs of the same project differ. Every run has a
`seed`: pass one when submitting to make the run repeatable, or omit it and the server picks
one and records it on the run.

```bash
# Same project + same seed = identical events
curl -s -X POST "http://127.0.0.1:8000/v1/projects/$PROJECT_ID/runs" \
  -H "Content-Type: application/json" -d '{"until": 36900, "seed": 42}'
```

To replay a run you didn't seed, read its `seed` from `GET /v1/runs/{id}` and resubmit with
it. Compare scenarios by using the same seed on both, so differences come from your change and
not from random draws. Reproducibility holds for a given version of spur.

## Project shape

A "project" is exactly `spur.io.schema.ProjectSpec` (components/routes/tours/trains) plus
API-owned metadata (`id`, `owner`, timestamps) - see `spur_api/schemas/project.py`. This is
deliberately not a divergent resource model: anything valid for `spur.io.formats.read_project_json`
is valid here.

## Authentication

Off by default. To require an API key on every endpoint except `/healthz` and `/readyz`:

```bash
SPUR_API_AUTH_ENABLED=true
SPUR_API_API_KEYS='["some-long-random-key"]'
```

Clients then send `Authorization: Bearer some-long-random-key`. A project's `owner` is
recorded as a short hash of the key that created it, never the key itself.

## Configuration

See `.env.example`.
