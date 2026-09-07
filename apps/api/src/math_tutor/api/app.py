"""FastAPI application factory and process-level application instance."""

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict
from sqlalchemy.engine import Engine

from math_tutor.adapters.db.engine import create_default_engine
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

    application = FastAPI(title="Math Practice Tutor API", version="0.1.0")
    application.state.engine = engine if engine is not None else create_default_engine()
    application.include_router(auth_router)

    @application.get("/health", response_model=HealthResponse, tags=["system"])
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    return application


app = create_app()
