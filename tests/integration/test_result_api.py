"""Integration tests for the result query and download API."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user_id, get_db
from app.api.v1.results import get_pandoc_converter
from app.main import create_app
from app.models import ParseResult as ORMResult
from app.models import ParseTask


class FakeResult:
    """Minimal DB result stub."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalar_one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None


class FakeConverter:
    """Pandoc converter stub."""

    async def convert(self, markdown: str, target_format: str) -> bytes:
        return f"<converted {target_format}>".encode()


def _task(user_id: uuid.UUID) -> ParseTask:
    return ParseTask(
        id=uuid.uuid4(),
        file_id=uuid.uuid4(),
        user_id=user_id,
        parser_type="txt",
        status="completed",
        progress=100,
    )


def _result(task_id: uuid.UUID, file_id: uuid.UUID, output_format: str) -> ORMResult:
    return ORMResult(
        id=uuid.uuid4(),
        task_id=task_id,
        file_id=file_id,
        output_format=output_format,
        output_text="hello" if output_format == "markdown" else '{"ok": true}',
        output_size=5,
    )


def _client(app: Any) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _override_app(
    db: Any,
    user_id: uuid.UUID,
    converter: FakeConverter | None = None,
) -> Any:
    app = create_app()

    async def override_get_db() -> Any:
        yield db

    async def override_get_user_id() -> uuid.UUID:
        return user_id

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_id] = override_get_user_id
    if converter is not None:
        app.dependency_overrides[get_pandoc_converter] = lambda: converter
    return app


@pytest.mark.asyncio
async def test_get_result_requires_auth() -> None:
    app = create_app()
    async with _client(app) as client:
        response = await client.get(f"/api/v1/results/{uuid.uuid4()}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_markdown_result_success() -> None:
    user_id = uuid.uuid4()
    task = _task(user_id)
    record = _result(task.id, task.file_id, "markdown")
    db = AsyncMock()
    db.execute.side_effect = [FakeResult([task]), FakeResult([record])]
    app = _override_app(db, user_id)

    async with _client(app) as client:
        response = await client.get(f"/api/v1/results/{task.id}?format=markdown")

    assert response.status_code == 200
    assert response.json()["data"]["output_text"] == "hello"


@pytest.mark.asyncio
async def test_get_result_forbidden_for_other_user() -> None:
    user_id = uuid.uuid4()
    task = _task(uuid.uuid4())
    db = AsyncMock()
    db.execute.side_effect = [FakeResult([task])]
    app = _override_app(db, user_id)

    async with _client(app) as client:
        response = await client.get(f"/api/v1/results/{task.id}")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_get_result_not_found() -> None:
    user_id = uuid.uuid4()
    task = _task(user_id)
    db = AsyncMock()
    db.execute.side_effect = [FakeResult([task]), FakeResult([])]
    app = _override_app(db, user_id)

    async with _client(app) as client:
        response = await client.get(f"/api/v1/results/{task.id}?format=json")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_download_markdown() -> None:
    user_id = uuid.uuid4()
    task = _task(user_id)
    record = _result(task.id, task.file_id, "markdown")
    db = AsyncMock()
    db.execute.side_effect = [FakeResult([task]), FakeResult([record])]
    app = _override_app(db, user_id)

    async with _client(app) as client:
        response = await client.get(f"/api/v1/results/{task.id}/download?format=markdown")

    assert response.status_code == 200
    assert response.text == "hello"
    assert response.headers["content-type"].startswith("text/markdown")


@pytest.mark.asyncio
async def test_download_html_uses_converter() -> None:
    user_id = uuid.uuid4()
    task = _task(user_id)
    markdown_record = _result(task.id, task.file_id, "markdown")
    db = AsyncMock()
    db.execute.side_effect = [FakeResult([task]), FakeResult([markdown_record])]
    app = _override_app(db, user_id, converter=FakeConverter())

    async with _client(app) as client:
        response = await client.get(f"/api/v1/results/{task.id}/download?format=html")

    assert response.status_code == 200
    assert response.text == "<converted html>"
    assert response.headers["content-type"].startswith("text/html")
