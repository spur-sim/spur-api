"""Async engine/session management.

Engine creation is deferred (not done at import time) and goes through a
module-level indirection - like `spur_api/deps.py`'s store lookup in
Phase 1 - so tests can point at a different database by calling
`configure_engine()` before the app or worker touches the database, without
needing to patch every call site individually.
"""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def configure_engine(database_url: str) -> None:
    global _engine, _session_factory
    _engine = create_async_engine(database_url, pool_pre_ping=True)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)


def get_engine() -> AsyncEngine:
    if _engine is None:
        from spur_api.config import settings

        configure_engine(settings.database_url)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    get_engine()  # ensures _session_factory is set as a side effect
    assert _session_factory is not None
    return _session_factory


async def get_db():
    """FastAPI dependency yielding one AsyncSession per request."""
    async with get_session_factory()() as session:
        yield session
