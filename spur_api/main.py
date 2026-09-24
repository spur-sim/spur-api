from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from spur_api.auth import current_principal
from spur_api.config import settings
from spur_api.exceptions import (
    InvalidProjectError,
    NotFoundError,
    RunAnalysisError,
    RunNotReadyError,
)
from spur_api.routers import health, projects, runs


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    yield
    await app.state.redis.aclose()


def create_app() -> FastAPI:
    app = FastAPI(title="spur-api", version="0.1.0", lifespan=lifespan)

    if settings.cors_origins:
        # Added before the routers so browser preflight (OPTIONS) requests
        # are answered here and never reach the auth dependency. No
        # credentials/cookies: clients authenticate with a bearer header.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["*"],
            allow_headers=["Authorization", "Content-Type"],
        )

    # Health endpoints stay unauthenticated (orchestrators probe them);
    # everything else requires a principal.
    app.include_router(health.router)
    app.include_router(projects.router, dependencies=[Depends(current_principal)])
    app.include_router(runs.router, dependencies=[Depends(current_principal)])

    @app.exception_handler(NotFoundError)
    def _not_found(request: Request, exc: NotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(InvalidProjectError)
    def _invalid_project(request: Request, exc: InvalidProjectError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(RunNotReadyError)
    def _run_not_ready(request: Request, exc: RunNotReadyError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(RunAnalysisError)
    def _run_analysis_error(request: Request, exc: RunAnalysisError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    return app


app = create_app()
