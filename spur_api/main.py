from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from spur_api.config import settings
from spur_api.exceptions import InvalidProjectError, NotFoundError
from spur_api.routers import health, projects, runs


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    yield
    await app.state.redis.aclose()


def create_app() -> FastAPI:
    app = FastAPI(title="spur-api", version="0.1.0", lifespan=lifespan)

    app.include_router(health.router)
    app.include_router(projects.router)
    app.include_router(runs.router)

    @app.exception_handler(NotFoundError)
    def _not_found(request: Request, exc: NotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(InvalidProjectError)
    def _invalid_project(request: Request, exc: InvalidProjectError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    return app


app = create_app()
