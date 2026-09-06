"""Tests for the API liveness contract."""

import pytest
from httpx2 import ASGITransport, AsyncClient

from math_tutor.api.app import create_app


@pytest.fixture
def anyio_backend() -> str:
    """Keep this unit test on the standard-library asyncio backend."""

    return "asyncio"


@pytest.mark.anyio
async def test_health_endpoint_reports_ok() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
