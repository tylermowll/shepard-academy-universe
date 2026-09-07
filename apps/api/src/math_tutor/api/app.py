"""FastAPI application factory and process-level application instance."""

import sqlite3
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

from math_tutor import settings
from math_tutor.adapters.db.engine import create_default_engine
from math_tutor.api.auth import origin_allowed
from math_tutor.api.auth import router as auth_router


class HealthResponse(BaseModel):
    """Public response returned by the liveness endpoint."""

    model_config = ConfigDict(frozen=True)

    status: str


def create_app(engine: Engine | None = None) -> FastAPI:
    """Create the API application without starting a server.

    ``engine`` defaults to the configured database so production serves the
    operator's file; tests pass an engine bound to an isolated temporary
    database instead. The liveness probe never requires the session secret.
    """

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        settings.session_secret()
        settings.app_public_origin()
        try:
            yield
        finally:
            if engine is None:
                application.state.engine.dispose()

    application = FastAPI(title="Math Practice Tutor API", version="0.1.0", lifespan=lifespan)
    application.state.engine = engine if engine is not None else create_default_engine()
    application.include_router(auth_router)

    @application.middleware("http")
    async def authentication_boundary(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        try:
            allowed = origin_allowed(request)
        except ValueError:
            response: Response = JSONResponse(
                {"detail": "Server authentication is not configured."}, status_code=500
            )
        else:
            response = (
                await call_next(request)
                if allowed
                else JSONResponse({"detail": "Origin not allowed."}, status_code=403)
            )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @application.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, _error: RequestValidationError) -> Response:
        # FastAPI's default validation details can echo password inputs.
        return JSONResponse({"detail": "Invalid request."}, status_code=422)

    @application.exception_handler(OperationalError)
    async def database_failure(_request: Request, error: OperationalError) -> Response:
        code = getattr(error.orig, "sqlite_errorcode", 0)
        if code & 0xFF in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
            return JSONResponse(
                {"detail": "Database is busy. Try again shortly."},
                status_code=503,
                headers={"Retry-After": "1"},
            )
        return JSONResponse({"detail": "Database is unavailable."}, status_code=503)

    @application.get("/health", response_model=HealthResponse, tags=["system"])
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    return application


app = create_app()
