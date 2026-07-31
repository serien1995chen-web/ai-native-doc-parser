"""Unit tests for the health endpoint."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.unit
async def test_health_returns_ok(client: AsyncClient) -> None:
    """The health endpoint returns status ok and version 1.0.0."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "1.0.0"}
