from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from spur_api.exceptions import InvalidProjectError, NotFoundError
from spur_api.routers import health, projects, runs


def create_app() -> FastAPI:
    app = FastAPI(title="spur-api", version="0.1.0")

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
