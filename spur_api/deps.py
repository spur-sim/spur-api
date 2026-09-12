from arq import ArqRedis
from fastapi import Request

from spur_api.db.session import get_db  # re-exported for router imports

__all__ = ["get_db", "get_redis"]


async def get_redis(request: Request) -> ArqRedis:
    return request.app.state.redis
