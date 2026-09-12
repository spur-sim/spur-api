from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz():
    return {"status": "ok"}


@router.get("/readyz")
def readyz():
    # No external dependencies (DB/Redis) exist yet in Phase 1, so
    # readiness and liveness are currently equivalent. Phase 2 adds
    # connectivity checks here once Postgres/Redis are real dependencies.
    return {"status": "ok"}
