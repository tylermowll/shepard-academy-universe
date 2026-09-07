"""FastAPI application factory and process-level application instance."""

import sqlite3
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from math_tutor import settings
from math_tutor.adapters.db.engine import create_default_engine
from math_tutor.adapters.db.models import WorkerHeartbeat
from math_tutor.adapters.db.types import utcnow
from math_tutor.adapters.providers.contracts import ProviderError
from math_tutor.api.auth import origin_allowed
from math_tutor.api.auth import router as auth_router
from math_tutor.api.learners import router as learner_router
from math_tutor.api.limits import BoundedBodies
from math_tutor.api.phone import router as phone_router
from math_tutor.api.photos import router as photo_router
from math_tutor.api.practice import router as practice_router
from math_tutor.api.profiles import router as profile_router
from math_tutor.api.providers import router as provider_router
from math_tutor.api.review import router as review_router
from math_tutor.api.setup import router as setup_router
from math_tutor.api.tutoring import router as tutoring_router
from math_tutor.setup_gate import SetupError, SetupGate


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
        from math_tutor.adapters.providers.config import load_configuration
        from math_tutor.retention import limits

        load_configuration()
        limits()
        try:
            yield
        finally:
            if engine is None:
                application.state.engine.dispose()

    application = FastAPI(title="Shepard Academy Universe API", version="0.1.0", lifespan=lifespan)
    application.add_middleware(BoundedBodies)
    application.state.setup_gate = SetupGate.from_environment()
    application.state.engine = engine if engine is not None else create_default_engine()
    application.include_router(auth_router)
    application.include_router(setup_router)
    application.include_router(learner_router)
    application.include_router(practice_router)
    application.include_router(tutoring_router)
    application.include_router(profile_router)
    application.include_router(photo_router)
    application.include_router(phone_router)
    application.include_router(provider_router)
    application.include_router(review_router)

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
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; font-src 'self'; connect-src 'self' https://huggingface.co https://*.huggingface.co https://*.hf.co https://raw.githubusercontent.com; worker-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        )
        return response

    @application.exception_handler(ProviderError)
    async def provider_error(_request: Request, error: ProviderError) -> Response:
        return JSONResponse({"detail": error.safe_message, "code": error.code}, status_code=422)

    @application.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, _error: RequestValidationError) -> Response:
        # FastAPI's default validation details can echo password inputs.
        return JSONResponse({"detail": "Invalid request."}, status_code=422)

    @application.exception_handler(SetupError)
    async def setup_error(_request: Request, error: SetupError) -> Response:
        headers = {"Retry-After": str(error.retry_after)} if error.retry_after is not None else None
        return JSONResponse(
            {"detail": error.safe_message, "code": error.code},
            status_code=error.status_code,
            headers=headers,
        )

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

    @application.get("/health/live", response_model=HealthResponse)
    def live() -> HealthResponse:
        return HealthResponse(status="ok")

    @application.get("/health/ready", response_model=HealthResponse)
    def ready() -> HealthResponse:
        with Session(application.state.engine) as db:
            db.execute(text("SELECT 1"))
            heartbeat = db.get(WorkerHeartbeat, "worker")
            if heartbeat is None or heartbeat.seen_at < utcnow() - timedelta(seconds=150):
                from fastapi import HTTPException

                raise HTTPException(503, "Worker unavailable.")
        return HealthResponse(status="ready")

    try:
        web_dist = settings.repository_root() / "apps/web/dist"
    except ValueError:
        web_dist = Path("/app/web")
    if web_dist.is_dir():
        application.mount("/assets", StaticFiles(directory=web_dist / "assets"), name="assets")

        @application.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(web_dist / "index.html", headers={"Cache-Control": "no-cache"})

        @application.get("/sw.js", include_in_schema=False)
        def service_worker() -> FileResponse:
            return FileResponse(
                web_dist / "sw.js",
                media_type="text/javascript",
                headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
            )

        @application.get("/manifest.webmanifest", include_in_schema=False)
        def manifest() -> FileResponse:
            return FileResponse(
                web_dist / "manifest.webmanifest", media_type="application/manifest+json"
            )

        @application.get("/icon.svg", include_in_schema=False)
        def icon() -> FileResponse:
            return FileResponse(web_dist / "icon.svg", media_type="image/svg+xml")

    return application


app = create_app()
