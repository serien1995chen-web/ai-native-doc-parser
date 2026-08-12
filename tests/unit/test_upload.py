"""Unit tests for the upload service and file metadata helpers."""

from __future__ import annotations

import base64
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_current_user_id
from app.core.config import settings
from app.core.exceptions import AppException
from app.models import File, User
from app.schemas.common import ErrorCode, FileStatus
from app.schemas.file import FileListParams
from app.services.storage import StorageService
from app.services.upload import UploadService


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.add = Mock()
    return db


class FakeStorage(StorageService):
    """In-memory storage used for unit tests."""

    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}
        self.deleted: list[str] = []

    async def save_bytes(self, relative_path: str, data: bytes) -> None:
        self.data[relative_path] = data

    async def save_text(self, relative_path: str, content: str) -> None:
        self.data[relative_path] = content.encode("utf-8")

    async def delete(self, relative_path: str) -> None:
        self.deleted.append(relative_path)
        self.data.pop(relative_path, None)

    async def read_bytes(self, relative_path: str) -> bytes:
        return self.data[relative_path]


class FailingStorage(FakeStorage):
    """Storage that fails on writes."""

    async def save_bytes(self, relative_path: str, data: bytes) -> None:
        raise OSError("disk full")

    async def save_text(self, relative_path: str, content: str) -> None:
        raise OSError("disk full")


class FakeResult:
    """Minimal async DB result stub."""

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


def _make_file(**overrides: Any) -> File:
    now = datetime.now(timezone.utc)
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "original_name": "a.txt",
        "uploaded_type": "file",
        "stored_path": "2026/01/01/a.txt",
        "file_size": 3,
        "status": "uploaded",
        "created_at": now,
        "updated_at": now,
    }
    values.update(overrides)
    return File(**values)


def _make_user(**overrides: Any) -> User:
    now = datetime.now(timezone.utc)
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "username": "user-1",
        "password_hash": "hash",
        "role": "user",
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    values.update(overrides)
    return User(**values)


def _service(db: AsyncMock, storage: FakeStorage | None = None) -> tuple[UploadService, FakeStorage]:
    fake_storage = storage or FakeStorage()
    return UploadService(fake_storage), fake_storage


@pytest.mark.asyncio
async def test_upload_file_success() -> None:
    db = _make_db()
    db.execute.return_value = FakeResult([])
    service, storage = _service(db)
    user_id = uuid.uuid4()

    response = await service.upload_file(db, user_id, "hello.txt", "text/plain", b"hello")

    assert response.original_name == "hello.txt"
    assert response.status == FileStatus.UPLOADED
    assert len(storage.data) == 1
    db.add.assert_called_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_upload_file_too_large(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _make_db()
    service, _ = _service(db)
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE", 3)

    with pytest.raises(AppException) as exc:
        await service.upload_file(db, uuid.uuid4(), "large.bin", None, b"1234")
    assert exc.value.code == ErrorCode.FILE_TOO_LARGE.value


@pytest.mark.asyncio
async def test_upload_file_duplicate_hash() -> None:
    db = _make_db()
    data = b"hello"
    existing = _make_file(file_hash=hashlib.sha256(data).hexdigest())
    db.execute.return_value = FakeResult([existing])
    service, _ = _service(db)

    with pytest.raises(AppException) as exc:
        await service.upload_file(db, uuid.uuid4(), "hello.txt", "text/plain", data)
    assert exc.value.code == ErrorCode.FILE_DUPLICATE.value


@pytest.mark.asyncio
async def test_upload_file_sanitizes_path_traversal() -> None:
    db = _make_db()
    db.execute.return_value = FakeResult([])
    service, storage = _service(db)

    response = await service.upload_file(db, uuid.uuid4(), "../evil.txt", "text/plain", b"x")

    assert response.original_name == "evil.txt"
    assert all(".." not in path for path in storage.data)


@pytest.mark.asyncio
async def test_upload_file_empty_name_becomes_file() -> None:
    db = _make_db()
    db.execute.return_value = FakeResult([])
    service, _ = _service(db)

    response = await service.upload_file(db, uuid.uuid4(), "", "text/plain", b"x")

    assert response.original_name == "file"


@pytest.mark.asyncio
async def test_upload_screenshot_success() -> None:
    db = _make_db()
    db.execute.return_value = FakeResult([])
    service, storage = _service(db)
    png_data = b"\x89PNG\r\n\x1a\n" + b"1234"
    payload = "data:image/png;base64," + base64.b64encode(png_data).decode()

    response = await service.upload_screenshot(db, uuid.uuid4(), payload)

    assert response.original_name == "screenshot.png"
    assert list(storage.data.values())[0] == png_data


@pytest.mark.asyncio
async def test_upload_screenshot_rejects_non_png_prefix() -> None:
    db = _make_db()
    service, _ = _service(db)

    with pytest.raises(AppException) as exc:
        await service.upload_screenshot(db, uuid.uuid4(), "data:image/jpeg;base64,xxx")
    assert exc.value.code == ErrorCode.UNSUPPORTED_FORMAT.value


@pytest.mark.asyncio
async def test_upload_screenshot_rejects_invalid_base64() -> None:
    db = _make_db()
    service, _ = _service(db)

    with pytest.raises(AppException) as exc:
        await service.upload_screenshot(
            db,
            uuid.uuid4(),
            "data:image/png;base64,not-valid!!",
        )
    assert exc.value.code == ErrorCode.UNSUPPORTED_FORMAT.value


@pytest.mark.asyncio
async def test_upload_screenshot_rejects_empty_data() -> None:
    db = _make_db()
    service, _ = _service(db)

    with pytest.raises(AppException) as exc:
        await service.upload_screenshot(db, uuid.uuid4(), "data:image/png;base64,")
    assert exc.value.code == ErrorCode.UNSUPPORTED_FORMAT.value


@pytest.mark.asyncio
async def test_upload_screenshot_rejects_non_png_magic() -> None:
    db = _make_db()
    service, _ = _service(db)
    fake_png = base64.b64encode(b"not a png").decode()

    with pytest.raises(AppException) as exc:
        await service.upload_screenshot(
            db,
            uuid.uuid4(),
            f"data:image/png;base64,{fake_png}",
        )
    assert exc.value.code == ErrorCode.UNSUPPORTED_FORMAT.value


@pytest.mark.asyncio
async def test_upload_file_storage_failure_rolls_back_and_no_record() -> None:
    db = _make_db()
    db.execute.return_value = FakeResult([])
    service = UploadService(FailingStorage())

    with pytest.raises(OSError):
        await service.upload_file(db, uuid.uuid4(), "a.txt", "text/plain", b"hello")

    db.add.assert_not_called()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_upload_file_commit_failure_rolls_back() -> None:
    db = _make_db()
    db.execute.return_value = FakeResult([])
    db.commit.side_effect = RuntimeError("commit failed")
    service, _ = _service(db)

    with pytest.raises(RuntimeError):
        await service.upload_file(db, uuid.uuid4(), "a.txt", "text/plain", b"hello")

    db.add.assert_called_once()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_upload_text_storage_failure_rolls_back_and_no_record() -> None:
    db = _make_db()
    db.execute.return_value = FakeResult([])
    service = UploadService(FailingStorage())

    with pytest.raises(OSError):
        await service.upload_text(db, uuid.uuid4(), "hello", "text")

    db.add.assert_not_called()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_upload_text_success() -> None:
    db = _make_db()
    db.execute.return_value = FakeResult([])
    service, storage = _service(db)

    response = await service.upload_text(db, uuid.uuid4(), "print('hi')", "code")

    assert response.original_name.endswith(".txt")
    assert list(storage.data.values())[0] == b"print('hi')"
    record = db.add.call_args.args[0]
    assert record.source_content == "print('hi')"
    assert record.file_hash == hashlib.sha256(b"print('hi')").hexdigest()


@pytest.mark.asyncio
async def test_upload_text_rejects_invalid_type_hint() -> None:
    db = _make_db()
    service, _ = _service(db)

    with pytest.raises(AppException) as exc:
        await service.upload_text(db, uuid.uuid4(), "hello", "doc")
    assert exc.value.code == ErrorCode.UNSUPPORTED_FORMAT.value


@pytest.mark.asyncio
async def test_upload_text_duplicate_returns_file_duplicate() -> None:
    db = _make_db()
    data = b"same text"
    existing = _make_file(file_hash=hashlib.sha256(data).hexdigest())
    db.execute.return_value = FakeResult([existing])
    service, _ = _service(db)

    with pytest.raises(AppException) as exc:
        await service.upload_text(db, uuid.uuid4(), "same text", "text")
    assert exc.value.code == ErrorCode.FILE_DUPLICATE.value


@pytest.mark.asyncio
async def test_upload_file_and_text_share_global_hash_space() -> None:
    db = _make_db()
    data = b"shared content"
    existing = _make_file(file_hash=hashlib.sha256(data).hexdigest())
    db.execute.return_value = FakeResult([existing])
    service, _ = _service(db)

    with pytest.raises(AppException) as exc:
        await service.upload_text(db, uuid.uuid4(), "shared content", "text")
    assert exc.value.code == ErrorCode.FILE_DUPLICATE.value


@pytest.mark.asyncio
async def test_upload_text_sets_content_type() -> None:
    db = _make_db()
    db.execute.return_value = FakeResult([])
    service, _ = _service(db)

    await service.upload_text(db, uuid.uuid4(), "hello", "text")
    await service.upload_text(db, uuid.uuid4(), "world", "code")

    added = db.add.call_args_list
    assert added[0].args[0].content_type == "text_block"
    assert added[1].args[0].content_type == "code"


@pytest.mark.asyncio
async def test_list_files_returns_paginated_response() -> None:
    db = _make_db()
    first = _make_file(original_name="report.pdf")
    second = _make_file(original_name="notes.txt")
    db.execute.side_effect = [FakeResult([first, second]), FakeResult([], total=2)]
    service, _ = _service(db)

    result = await service.list_files(
        db,
        uuid.uuid4(),
        FileListParams(page=1, limit=10, search="report", status=FileStatus.UPLOADED),
    )

    assert result.total == 2
    assert len(result.items) == 2
    assert result.items[0].original_name == "report.pdf"


@pytest.mark.asyncio
async def test_list_files_builds_filter_and_sort_query() -> None:
    db = _make_db()
    db.execute.side_effect = [FakeResult([]), FakeResult([], total=0)]
    service, _ = _service(db)
    user_id = uuid.uuid4()

    await service.list_files(
        db,
        user_id,
        FileListParams(
            page=2,
            limit=5,
            search="report",
            status=FileStatus.UPLOADED,
            sort="created_at:desc",
        ),
    )

    statement = db.execute.call_args_list[0].args[0]
    compiled = str(
        statement.compile(
            compile_kwargs={"literal_binds": True},
            dialect=postgresql.dialect(),
        )
    )
    assert "files.status =" in compiled
    assert "ILIKE" in compiled
    assert "ORDER BY files.created_at DESC" in compiled
    assert "LIMIT 5" in compiled
    assert "OFFSET 5" in compiled


@pytest.mark.asyncio
async def test_get_file_success() -> None:
    db = _make_db()
    file = _make_file()
    db.execute.return_value = FakeResult([file])
    service, _ = _service(db)

    response = await service.get_file(db, uuid.uuid4(), file.id)

    assert response.file_id == file.id
    assert response.original_name == file.original_name


@pytest.mark.asyncio
async def test_get_file_not_found() -> None:
    db = _make_db()
    db.execute.return_value = FakeResult([])
    service, _ = _service(db)

    with pytest.raises(AppException) as exc:
        await service.get_file(db, uuid.uuid4(), uuid.uuid4())
    assert exc.value.code == ErrorCode.FILE_NOT_FOUND.value


@pytest.mark.asyncio
async def test_delete_file_success() -> None:
    db = _make_db()
    file = _make_file(stored_path="2026/01/01/a.txt")
    db.execute.return_value = FakeResult([file])
    service, storage = _service(db)
    storage.data[file.stored_path] = b"content"

    await service.delete_file(db, uuid.uuid4(), file.id)

    assert storage.deleted == [file.stored_path]
    db.delete.assert_awaited_once_with(file)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_file_not_found() -> None:
    db = _make_db()
    db.execute.return_value = FakeResult([])
    service, _ = _service(db)

    with pytest.raises(AppException) as exc:
        await service.delete_file(db, uuid.uuid4(), uuid.uuid4())
    assert exc.value.code == ErrorCode.FILE_NOT_FOUND.value


@pytest.mark.asyncio
async def test_delete_file_storage_failure_keeps_db_record() -> None:
    db = _make_db()
    file = _make_file(stored_path="2026/01/01/a.txt")
    db.execute.return_value = FakeResult([file])
    storage = FakeStorage()
    storage.data[file.stored_path] = b"content"

    async def fail_delete(relative_path: str) -> None:
        raise OSError("delete failed")

    storage.delete = fail_delete
    service = UploadService(storage)

    with pytest.raises(OSError):
        await service.delete_file(db, uuid.uuid4(), file.id)

    db.delete.assert_not_called()


@pytest.mark.asyncio
async def test_get_current_user_id_jwt_user_exists() -> None:
    db = _make_db()
    user = _make_user()
    db.execute.return_value = FakeResult([user])

    result = await get_current_user_id(db, identity=str(user.id))

    assert result == user.id


@pytest.mark.asyncio
async def test_get_current_user_id_invalid_identity() -> None:
    db = _make_db()

    with pytest.raises(AppException) as exc:
        await get_current_user_id(db, identity="not-a-uuid")
    assert exc.value.code == ErrorCode.UNAUTHORIZED.value


@pytest.mark.asyncio
async def test_get_current_user_id_api_key_creates_user() -> None:
    db = _make_db()
    db.execute.return_value = FakeResult([])

    result = await get_current_user_id(db, identity="api-key")

    assert isinstance(result, uuid.UUID)
    db.add.assert_called_once()
    db.commit.assert_awaited_once()
    assert db.add.call_args.args[0].username == "api-key"


@pytest.mark.asyncio
async def test_get_current_user_id_api_key_existing_user() -> None:
    db = _make_db()
    user = _make_user(username="api-key")
    db.execute.return_value = FakeResult([user])

    result = await get_current_user_id(db, identity="api-key")

    assert result == user.id
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_get_current_user_id_api_key_concurrent_insert_rolls_back_and_requeries() -> None:
    db = _make_db()
    existing = _make_user(username="api-key")
    db.execute.side_effect = [FakeResult([]), FakeResult([existing])]
    db.commit.side_effect = IntegrityError("INSERT", {}, Exception("duplicate"))

    result = await get_current_user_id(db, identity="api-key")

    assert result == existing.id
    db.add.assert_called_once()
    db.rollback.assert_awaited_once()
