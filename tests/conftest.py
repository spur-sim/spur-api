import json
import os
import pathlib

# Must happen before any `spur_api` import instantiates the Settings
# singleton - point the whole test session at scratch Postgres/Redis
# instances, separate from whatever a developer's own .env configures.
os.environ.setdefault(
    "SPUR_API_DATABASE_URL", "postgresql+asyncpg://spur:spur@localhost:5433/spur_api_test"
)
os.environ.setdefault("SPUR_API_REDIS_URL", "redis://localhost:6380/0")

import pytest
import pytest_asyncio
import redis.asyncio as aioredis
from httpx import ASGITransport, AsyncClient

from spur_api.db.base import Base
from spur_api.db.session import configure_engine, get_engine, get_session_factory
from spur_api.main import create_app
from spur_api.worker.tasks import run_simulation

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def line4_project_dict():
    with open(FIXTURES / "line4_project.json") as f:
        return json.load(f)


@pytest_asyncio.fixture
async def db_engine():
    # Configured (and schema recreated) inside the current test's event
    # loop, deliberately: an httpx.AsyncClient over ASGITransport runs the
    # whole app in-process on this same loop (no separate thread, unlike
    # the sync TestClient), so the async engine it lazily creates via
    # get_engine()/get_db() must be bound to this same loop too - asyncpg
    # connections aren't shareable across loops.
    configure_engine(os.environ["SPUR_API_DATABASE_URL"])
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _flush_redis():
    r = aioredis.from_url(os.environ["SPUR_API_REDIS_URL"])
    await r.flushdb()
    yield
    await r.aclose()


@pytest_asyncio.fixture
async def client(db_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest.fixture
def run_worker():
    """Execute the arq job function directly against the test database,
    bypassing the real queue - exercises SpurRunner + persistence exactly
    as a live worker process would, without needing one running. Shares
    `db_engine`'s loop-bound session factory via `get_session_factory()`.
    """

    async def _run(run_id: str) -> None:
        await run_simulation({"session_factory": get_session_factory()}, run_id)

    return _run
