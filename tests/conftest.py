"""Shared pytest fixtures for the backend test suite."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, Mock

import pytest
from app.main import create_app
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """Provide an async HTTP client for the FastAPI application."""
    application = create_app()
    transport = ASGITransport(app=application)
    test_client = AsyncClient(transport=transport, base_url="http://test")
    yield test_client
    await test_client.aclose()


@pytest.fixture
def db_session_mock() -> AsyncMock:
    """Provide an async mock database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def minio_mock() -> Mock:
    """Provide a mock MinIO client with common object methods."""
    return Mock(
        put_object=Mock(),
        get_object=Mock(),
        remove_object=Mock(),
        fput_object=Mock(),
        presigned_get_object=Mock(),
    )
