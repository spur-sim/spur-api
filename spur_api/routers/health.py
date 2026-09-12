from arq import ArqRedis
from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from spur_api.deps import get_db, get_redis

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz():
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: ArqRedis = Depends(get_redis),
):
    checks = {}
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:  # noqa: BLE001 - report, don't crash the check
        checks["database"] = f"error: {e}"

    try:
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as e:  # noqa: BLE001
        checks["redis"] = f"error: {e}"

    if any(v != "ok" for v in checks.values()):
        response.status_code = 503
    return checks
