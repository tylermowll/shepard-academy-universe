"""FastAPI application factory and process-level application instance."""

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """Public response returned by the liveness endpoint."""

    model_config = ConfigDict(frozen=True)

    status: str


def create_app() -> FastAPI:
    """Create the API application without starting a server."""

    application = FastAPI(title="Math Practice Tutor API", version="0.1.0")

    @application.get("/health", response_model=HealthResponse, tags=["system"])
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    return application


app = create_app()
