"""Integration tests for the file upload API using fake DB and storage."""

from __future__ import annotations

import base64
import re
import uuid
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects import postgresql

from app.api.deps import get_current_user_id, get_db
from app.api.v1.files import get_file_type_id_service, get_storage_service
from app.core.config import settings
from app.core.security import create_access_token
from app.main import create_app
from app.models import File
from app.schemas.identification import IdentificationResult
from app.services.storage import LocalStorageService


class FakeIdentifier:
    """Stand-in identification service for API integration tests."""

    async def identify(
        self,
        db: Any,
        file_id: uuid.UUID,
        path: Path,
        uploaded_type: str | None = None,
    ) -> IdentificationResult:
        return IdentificationResult(
            file_id=file_id,
            identified_type="txt",
            content_type="text_block",
            identified_confidence=0.85,
            final_layer=3,
            is_final=True,
        )


class FakeResult:
    """Result stub used by FakeAsyncSession."""

    def __init__(self, rows: list[Any], total: int | None = None) -> None:
        self._rows = rows
        self._total = len(rows) if total is None else total

    def scalar_one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None

    def scalar_one(self) -> Any:
        return self._total

    def scalars(self) -> FakeResult:
        return self

    def all(self) -> list[Any]:
        return self._rows


class FakeAsyncSession:
    """In-memory session supporting the A-4 file queries."""

    def __init__(self) -> None:
        self.files: list[File] = []
        self.added: list[Any] = []
        self.deleted: list[Any] = []
        self.commit_count = 0

    def _matching_files(self, sql: str) -> list[File]:
        rows = list(self.files)
        user_match = re.search(r"files\.user_id = '([^']+)'", sql)
        if user_match:
            rows = [row for row in rows if str(row.user_id) == user_match.group(1)]
        hash_match = re.search(r"files\.file_hash = '([^']+)'", sql)
        if hash_match:
            rows = [row for row in rows if row.file_hash == hash_match.group(1)]
        id_match = re.search(r"files\.id = '([^']+)'", sql)
        if id_match:
            rows = [row for row in rows if str(row.id) == id_match.group(1)]
        status_match = re.search(r"files\.status = '([^']+)'", sql)
        if status_match:
            rows = [row for row in rows if row.status == status_match.group(1)]
        pattern_match = re.search(r"'%([^']*)%'", sql)
        if pattern_match:
            pattern = pattern_match.group(1).replace("%", "").lower()
            rows = [row for row in rows if pattern in row.original_name.lower()]
        return rows

    async def execute(self, statement: Any) -> FakeResult:
        compiled = statement.compile(
            compile_kwargs={"literal_binds": True},
            dialect=postgresql.dialect(),
        )
        sql = str(compiled)

        if "count(" in sql.lower():
            return FakeResult([], total=len(self._matching_files(sql)))

        rows = self._matching_files(sql)
        order_match = re.search(r"ORDER BY files\.(\w+) (ASC|DESC)", sql)
        if order_match:
            column, direction = order_match.groups()
            rows = sorted(
                rows,
                key=lambda row: getattr(row, column),
                reverse=(direction == "DESC"),
            )
        limit_match = re.search(r"LIMIT (\d+)", sql)
        offset_match = re.search(r"OFFSET (\d+)", sql)
        if offset_match:
            rows = rows[int(offset_match.group(1)) :]
        if limit_match:
            rows = rows[: int(limit_match.group(1))]
        return FakeResult(rows)

    def add(self, obj: Any) -> None:
        self.added.append(obj)
        if isinstance(obj, File):
            self.files.append(obj)

    async def delete(self, obj: Any) -> None:
        self.deleted.append(obj)
        if isinstance(obj, File):
            self.files = [row for row in self.files if row.id != obj.id]

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        return None

    async def close(self) -> None:
        return None


@pytest.fixture
def api_context(tmp_path: Path) -> tuple[Any, FakeAsyncSession, LocalStorageService, uuid.UUID]:
    app = create_app()
    db = FakeAsyncSession()
    storage = LocalStorageService(root=tmp_path)
    user_id = uuid.uuid4()

    async def override_get_db() -> Any:
        yield db

    async def override_get_user_id() -> uuid.UUID:
        return user_id

    def override_storage() -> LocalStorageService:
        return storage

    def override_file_type_id() -> FakeIdentifier:
        return FakeIdentifier()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_id] = override_get_user_id
    app.dependency_overrides[get_storage_service] = override_storage
    app.dependency_overrides[get_file_type_id_service] = override_file_type_id
    return app, db, storage, user_id


async def _client(app: Any) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_upload_without_auth_returns_401() -> None:
    app = create_app()
    async with await _client(app) as client:
        response = await client.post(
            "/api/v1/files/upload",
            files={"file": ("a.txt", b"hello", "text/plain")},
        )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_upload_with_jwt_sub_api_key_returns_401() -> None:
    app = create_app()
    db = FakeAsyncSession()

    async def override_get_db() -> Any:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    token = create_access_token("api-key")
    async with await _client(app) as client:
        response = await client.post(
            "/api/v1/files/upload",
            files={"file": ("a.txt", b"hello", "text/plain")},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_upload_file_success(api_context: Any) -> None:
    app, db, storage, _ = api_context
    async with await _client(app) as client:
        response = await client.post(
            "/api/v1/files/upload",
            files={"file": ("hello.txt", b"hello", "text/plain")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "parsing"
    assert len(db.files) == 1
    assert len([path for path in storage.root.rglob("*") if path.is_file()]) == 1


@pytest.mark.asyncio
async def test_upload_duplicate_returns_409(api_context: Any) -> None:
    app, _, _, _ = api_context
    async with await _client(app) as client:
        first = await client.post(
            "/api/v1/files/upload",
            files={"file": ("a.txt", b"same", "text/plain")},
        )
        second = await client.post(
            "/api/v1/files/upload",
            files={"file": ("b.txt", b"same", "text/plain")},
        )
    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "FILE_DUPLICATE"


@pytest.mark.asyncio
async def test_upload_file_too_large(api_context: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    app, _, _, _ = api_context
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE", 3)
    async with await _client(app) as client:
        response = await client.post(
            "/api/v1/files/upload",
            files={"file": ("big.txt", b"1234", "text/plain")},
        )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


@pytest.mark.asyncio
async def test_upload_screenshot_success(api_context: Any) -> None:
    app, db, _, _ = api_context
    png_data = b"\x89PNG\r\n\x1a\n" + b"image"
    payload = {
        "image_base64": "data:image/png;base64,"
        + base64.b64encode(png_data).decode()
    }
    async with await _client(app) as client:
        response = await client.post("/api/v1/files/upload/screenshot", json=payload)
    assert response.status_code == 200
    assert response.json()["data"]["original_name"] == "screenshot.png"
    assert len(db.files) == 1


@pytest.mark.asyncio
async def test_upload_screenshot_rejects_invalid_data(api_context: Any) -> None:
    app, _, _, _ = api_context
    async with await _client(app) as client:
        response = await client.post(
            "/api/v1/files/upload/screenshot",
            json={"image_base64": "data:image/jpeg;base64,xxx"},
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_FORMAT"


@pytest.mark.asyncio
async def test_upload_screenshot_duplicate_returns_409(api_context: Any) -> None:
    app, _, _, _ = api_context
    png_data = b"\x89PNG\r\n\x1a\n" + b"same-image"
    payload = {
        "image_base64": "data:image/png;base64,"
        + base64.b64encode(png_data).decode()
    }
    async with await _client(app) as client:
        first = await client.post("/api/v1/files/upload/screenshot", json=payload)
        second = await client.post("/api/v1/files/upload/screenshot", json=payload)
    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "FILE_DUPLICATE"


@pytest.mark.asyncio
async def test_upload_text_success(api_context: Any) -> None:
    app, db, _, _ = api_context
    async with await _client(app) as client:
        response = await client.post(
            "/api/v1/files/upload/text",
            json={"content": "print('hi')", "type_hint": "code"},
        )
    assert response.status_code == 200
    assert response.json()["data"]["original_name"].endswith(".txt")
    assert db.files[0].source_content == "print('hi')"
    assert db.files[0].content_type == "code"
    assert db.files[0].file_hash


@pytest.mark.asyncio
async def test_upload_text_duplicate_returns_409(api_context: Any) -> None:
    app, _, _, _ = api_context
    async with await _client(app) as client:
        first = await client.post(
            "/api/v1/files/upload/text",
            json={"content": "same text", "type_hint": "text"},
        )
        second = await client.post(
            "/api/v1/files/upload/text",
            json={"content": "same text", "type_hint": "text"},
        )
    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "FILE_DUPLICATE"


@pytest.mark.asyncio
async def test_list_files_filters_and_paginates(api_context: Any) -> None:
    app, _, _, _ = api_context
    async with await _client(app) as client:
        await client.post(
            "/api/v1/files/upload",
            files={"file": ("report.txt", b"one", "text/plain")},
        )
        await client.post(
            "/api/v1/files/upload",
            files={"file": ("notes.txt", b"two", "text/plain")},
        )
        response = await client.get(
            "/api/v1/files",
            params={"search": "report", "status": "parsing", "sort": "created_at:desc"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["original_name"] == "report.txt"


@pytest.mark.asyncio
async def test_get_file_success(api_context: Any) -> None:
    app, db, _, _ = api_context
    async with await _client(app) as client:
        upload = await client.post(
            "/api/v1/files/upload",
            files={"file": ("a.txt", b"hello", "text/plain")},
        )
        file_id = upload.json()["data"]["file_id"]
        response = await client.get(f"/api/v1/files/{file_id}")
    assert response.status_code == 200
    assert response.json()["data"]["file_id"] == file_id


@pytest.mark.asyncio
async def test_get_file_not_found(api_context: Any) -> None:
    app, _, _, _ = api_context
    async with await _client(app) as client:
        response = await client.get(f"/api/v1/files/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "FILE_NOT_FOUND"


@pytest.mark.asyncio
async def test_delete_file_success(api_context: Any) -> None:
    app, db, storage, _ = api_context
    async with await _client(app) as client:
        upload = await client.post(
            "/api/v1/files/upload",
            files={"file": ("a.txt", b"hello", "text/plain")},
        )
        file_id = upload.json()["data"]["file_id"]
        deleted = await client.delete(f"/api/v1/files/{file_id}")
        missing = await client.get(f"/api/v1/files/{file_id}")
    assert deleted.status_code == 200
    assert deleted.json()["success"] is True
    assert missing.status_code == 404
    assert len(db.files) == 0
    assert not list(storage.root.rglob("*"))


@pytest.mark.asyncio
async def test_list_files_rejects_invalid_pagination(api_context: Any) -> None:
    app, _, _, _ = api_context
    async with await _client(app) as client:
        too_large = await client.get("/api/v1/files", params={"limit": 101})
        zero_page = await client.get("/api/v1/files", params={"page": 0})
    assert too_large.status_code == 422
    assert zero_page.status_code == 422
