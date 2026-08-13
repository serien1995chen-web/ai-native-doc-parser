"""Unit tests for the parser router and arq worker tasks."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.dialects import postgresql

from app.core.exceptions import AppException
from app.models import File, ParseResult as ORMResult, ParseTask
from app.parsers import ParserRegistry
from app.parsers.base import BaseParser, ParseResult, ParserInfo
from app.schemas.common import ErrorCode
from app.services.parser_router import ParserRouter
from app.services.storage import StorageService
from app.services.task_queue import PARSE_IMAGE_TASK, PARSE_PDF_TASK
from app.worker import WorkerSettings, parse_image_task, parse_pdf_task


class FakeResult:
    """Minimal DB result stub."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalar_one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None


class FakeStorage(StorageService):
    """Storage stub returning a fixed path."""

    def resolve_path(self, relative_path: str) -> Path:
        return Path(relative_path)

    async def save_bytes(self, relative_path: str, data: bytes) -> None:
        raise NotImplementedError

    async def save_text(self, relative_path: str, content: str) -> None:
        raise NotImplementedError

    async def delete(self, relative_path: str) -> None:
        raise NotImplementedError

    async def read_bytes(self, relative_path: str) -> bytes:
        raise NotImplementedError


class FakeDB:
    """In-memory session supporting parser router queries."""

    def __init__(
        self,
        file: File | None,
        fail_on_commit: int | None = None,
    ) -> None:
        self.file = file
        self.added: list[Any] = []
        self.pending: list[Any] = []
        self.committed: list[Any] = []
        self.commits = 0
        self.rollbacks = 0
        self.fail_on_commit = fail_on_commit
        self.executed: list[Any] = []

    async def execute(self, statement: Any) -> FakeResult:
        self.executed.append(statement)
        return FakeResult([self.file] if self.file is not None else [])

    def add(self, obj: Any) -> None:
        self.added.append(obj)
        self.pending.append(obj)

    async def commit(self) -> None:
        self.commits += 1
        if self.fail_on_commit is not None and self.commits == self.fail_on_commit:
            raise RuntimeError("commit failed")
        self.committed.extend(self.pending)
        self.pending.clear()

    async def rollback(self) -> None:
        self.rollbacks += 1
        self.pending.clear()


class StubParser(BaseParser):
    """Parser stub for router tests."""

    def __init__(self, supported_types: list[str], fail: bool = False) -> None:
        self._info = ParserInfo(
            name="stub",
            supported_types=supported_types,
            required_gpu=False,
            required_models=[],
            version="1.0",
        )
        self.fail = fail
        self.calls = 0

    def info(self) -> ParserInfo:
        return self._info

    def parse(
        self,
        file_path: str,
        options: dict[str, Any] | None = None,
    ) -> ParseResult:
        self.calls += 1
        if self.fail:
            raise RuntimeError("parse failed")
        return ParseResult(markdown="", json_data={})


def _make_file() -> File:
    return File(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        original_name="a.txt",
        uploaded_type="file",
        stored_path="2026/01/01/a.txt",
        status="parsing",
    )


def _make_task(file_id: uuid.UUID, user_id: uuid.UUID) -> ParseTask:
    return ParseTask(
        id=uuid.uuid4(),
        file_id=file_id,
        user_id=user_id,
        parser_type="pdf",
        status="queued",
        progress=0,
        retry_count=0,
    )


@pytest.fixture(autouse=True)
def _clear_registry() -> None:
    ParserRegistry._parsers.clear()
    yield
    ParserRegistry._parsers.clear()


@pytest.mark.asyncio
async def test_sync_parser_executes_and_updates_status() -> None:
    parser = StubParser(supported_types=["txt"])
    ParserRegistry.register(parser)
    file = _make_file()
    db = FakeDB(file)
    router = ParserRouter(storage=FakeStorage())

    await router.route(db, file.id, "txt", file.user_id)

    assert parser.calls == 1
    task = db.added[0]
    assert task.status == "completed"
    assert task.progress == 100
    assert file.status == "completed"
    assert len(db.added) == 3


@pytest.mark.asyncio
async def test_sync_parser_failure_marks_failed() -> None:
    parser = StubParser(supported_types=["txt"], fail=True)
    ParserRegistry.register(parser)
    file = _make_file()
    db = FakeDB(file)
    router = ParserRouter(storage=FakeStorage())

    with pytest.raises(AppException) as exc:
        await router.route(db, file.id, "txt", file.user_id)

    assert exc.value.code == ErrorCode.PARSER_FAILED.value
    task = db.added[0]
    assert task.status == "failed"
    assert file.status == "failed"


@pytest.mark.asyncio
async def test_sync_parser_final_commit_failure_discards_results() -> None:
    parser = StubParser(supported_types=["txt"])
    ParserRegistry.register(parser)
    file = _make_file()
    db = FakeDB(file, fail_on_commit=3)
    router = ParserRouter(storage=FakeStorage())

    with pytest.raises(AppException) as exc:
        await router.route(db, file.id, "txt", file.user_id)

    assert exc.value.code == ErrorCode.PARSER_FAILED.value
    task = db.added[0]
    assert task.status == "failed"
    assert file.status == "failed"
    assert db.rollbacks == 1
    assert any(isinstance(row, ORMResult) for row in db.added)
    assert not any(isinstance(row, ORMResult) for row in db.committed)


@pytest.mark.asyncio
async def test_async_pdf_creates_task_and_enqueues() -> None:
    file = _make_file()
    db = FakeDB(file)
    router = ParserRouter(storage=FakeStorage())

    with patch("app.services.parser_router.enqueue_job", new=AsyncMock()) as enqueue:
        await router.route(db, file.id, "pdf", file.user_id)

    enqueue.assert_awaited_once_with(PARSE_PDF_TASK, file_id=str(file.id))
    task = db.added[0]
    assert task.status == "queued"


@pytest.mark.asyncio
async def test_rerun_task_clears_old_results_before_requeue() -> None:
    file = _make_file()
    task = _make_task(file.id, file.user_id)
    task.status = "queued"
    db = FakeDB(file)
    router = ParserRouter(storage=FakeStorage())

    with patch(
        "app.services.parser_router.enqueue_job",
        new=AsyncMock(),
    ) as enqueue:
        await router.rerun_task(db, task, file, "pdf")

    enqueue.assert_awaited_once_with(PARSE_PDF_TASK, file_id=str(file.id))
    statements = [
        str(
            statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        for statement in db.executed
    ]
    assert any("DELETE FROM parse_results" in sql for sql in statements)


@pytest.mark.asyncio
async def test_async_image_creates_task_and_enqueues() -> None:
    file = _make_file()
    db = FakeDB(file)
    router = ParserRouter(storage=FakeStorage())

    with patch("app.services.parser_router.enqueue_job", new=AsyncMock()) as enqueue:
        await router.route(db, file.id, "image", file.user_id)

    enqueue.assert_awaited_once_with(PARSE_IMAGE_TASK, file_id=str(file.id))
    task = db.added[0]
    assert task.status == "queued"


@pytest.mark.asyncio
async def test_async_enqueue_failure_marks_failed() -> None:
    file = _make_file()
    db = FakeDB(file)
    router = ParserRouter(storage=FakeStorage())

    with patch(
        "app.services.parser_router.enqueue_job",
        new=AsyncMock(side_effect=RuntimeError("redis down")),
    ):
        with pytest.raises(AppException) as exc:
            await router.route(db, file.id, "pdf", file.user_id)

    assert exc.value.code == ErrorCode.PARSER_FAILED.value
    task = db.added[0]
    assert task.status == "failed"
    assert file.status == "failed"


@pytest.mark.asyncio
async def test_unsupported_type_marks_file_failed() -> None:
    file = _make_file()
    db = FakeDB(file)
    router = ParserRouter(storage=FakeStorage())

    with pytest.raises(AppException) as exc:
        await router.route(db, file.id, "unknown", file.user_id)

    assert exc.value.code == ErrorCode.UNSUPPORTED_FORMAT.value
    assert file.status == "failed"
    assert db.added == []


@pytest.mark.asyncio
async def test_missing_file_raises_not_found() -> None:
    db = FakeDB(None)
    router = ParserRouter(storage=FakeStorage())

    with pytest.raises(AppException) as exc:
        await router.route(db, uuid.uuid4(), "txt", uuid.uuid4())
    assert exc.value.code == ErrorCode.FILE_NOT_FOUND.value


class FakeWorkerSession:
    """Async session stub for worker tests."""

    def __init__(
        self,
        file: File,
        task: ParseTask,
        fail_on_commit: int | None = None,
    ) -> None:
        self.file = file
        self.task = task
        self.commits = 0
        self.rollbacks = 0
        self.added: list[Any] = []
        self.pending: list[Any] = []
        self.committed: list[Any] = []
        self.fail_on_commit = fail_on_commit

    async def __aenter__(self) -> FakeWorkerSession:
        return self

    async def __aexit__(self, *args: Any) -> bool:
        return False

    async def execute(self, statement: Any) -> FakeResult:
        sql = str(statement)
        if "FROM parse_tasks" in sql:
            return FakeResult([self.task])
        return FakeResult([self.file])

    async def commit(self) -> None:
        self.commits += 1
        if self.fail_on_commit is not None and self.commits == self.fail_on_commit:
            raise RuntimeError("commit failed")
        self.committed.extend(self.pending)
        self.pending.clear()

    async def rollback(self) -> None:
        self.rollbacks += 1
        self.pending.clear()

    async def close(self) -> None:
        return None

    def add(self, obj: Any) -> None:
        self.added.append(obj)
        self.pending.append(obj)


@pytest.mark.asyncio
async def test_worker_retries_after_parser_failure() -> None:
    parser = StubParser(supported_types=["pdf"], fail=True)
    ParserRegistry.register(parser)
    file = _make_file()
    task = _make_task(file.id, file.user_id)
    session = FakeWorkerSession(file, task)

    with patch("app.worker.AsyncSessionLocal", return_value=session), patch(
        "app.worker.enqueue_job",
        new=AsyncMock(),
    ) as enqueue:
        await parse_pdf_task({}, str(file.id))

    assert task.retry_count == 1
    assert task.status == "queued"
    enqueue.assert_awaited_once_with(
        PARSE_PDF_TASK,
        file_id=str(file.id),
        _defer_by=2,
    )


@pytest.mark.asyncio
async def test_worker_retry_after_manual_retry_increments_count() -> None:
    parser = StubParser(supported_types=["pdf"], fail=True)
    ParserRegistry.register(parser)
    file = _make_file()
    task = _make_task(file.id, file.user_id)
    task.retry_count = 1
    session = FakeWorkerSession(file, task)

    with patch("app.worker.AsyncSessionLocal", return_value=session), patch(
        "app.worker.enqueue_job",
        new=AsyncMock(),
    ) as enqueue:
        await parse_pdf_task({}, str(file.id))

    assert task.retry_count == 2
    assert task.status == "queued"
    enqueue.assert_awaited_once_with(
        PARSE_PDF_TASK,
        file_id=str(file.id),
        _defer_by=4,
    )


@pytest.mark.asyncio
async def test_worker_success_marks_completed() -> None:
    parser = StubParser(supported_types=["pdf"])
    ParserRegistry.register(parser)
    file = _make_file()
    task = _make_task(file.id, file.user_id)
    session = FakeWorkerSession(file, task)

    with patch("app.worker.AsyncSessionLocal", return_value=session):
        await parse_pdf_task({}, str(file.id))

    assert task.status == "completed"
    assert task.progress == 100
    assert file.status == "completed"
    assert len(session.added) == 2


@pytest.mark.asyncio
async def test_worker_reenqueue_failure_writes_error_details() -> None:
    parser = StubParser(supported_types=["pdf"], fail=True)
    ParserRegistry.register(parser)
    file = _make_file()
    task = _make_task(file.id, file.user_id)
    session = FakeWorkerSession(file, task)

    with patch("app.worker.AsyncSessionLocal", return_value=session), patch(
        "app.worker.enqueue_job",
        new=AsyncMock(side_effect=RuntimeError("redis down")),
    ):
        await parse_pdf_task({}, str(file.id))

    assert task.status == "failed"
    assert file.status == "failed"
    assert task.error_message.startswith("Failed to re-enqueue job:")
    assert task.error_details == {"type": "RuntimeError"}


@pytest.mark.asyncio
async def test_worker_marks_failed_after_retry_limit() -> None:
    parser = StubParser(supported_types=["pdf"], fail=True)
    ParserRegistry.register(parser)
    file = _make_file()
    task = _make_task(file.id, file.user_id)
    task.retry_count = 2
    session = FakeWorkerSession(file, task)

    with patch("app.worker.AsyncSessionLocal", return_value=session), patch(
        "app.worker.enqueue_job",
        new=AsyncMock(),
    ) as enqueue:
        await parse_pdf_task({}, str(file.id))

    assert task.retry_count == 3
    assert task.status == "failed"
    assert file.status == "failed"
    enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_worker_final_commit_failure_discards_results() -> None:
    parser = StubParser(supported_types=["pdf"])
    ParserRegistry.register(parser)
    file = _make_file()
    task = _make_task(file.id, file.user_id)
    task.retry_count = 2
    session = FakeWorkerSession(file, task, fail_on_commit=2)

    with patch("app.worker.AsyncSessionLocal", return_value=session), patch(
        "app.worker.enqueue_job",
        new=AsyncMock(),
    ) as enqueue:
        await parse_pdf_task({}, str(file.id))

    assert task.retry_count == 3
    assert task.status == "failed"
    assert file.status == "failed"
    assert session.rollbacks == 1
    assert any(isinstance(row, ORMResult) for row in session.added)
    assert not any(isinstance(row, ORMResult) for row in session.committed)
    enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_worker_image_parser_missing_marks_failed() -> None:
    file = _make_file()
    task = _make_task(file.id, file.user_id)
    task.parser_type = "image"
    session = FakeWorkerSession(file, task)

    with patch("app.worker.AsyncSessionLocal", return_value=session):
        await parse_image_task({}, str(file.id))

    assert task.status == "failed"
    assert file.status == "failed"


def test_worker_redis_settings_derived_from_settings_url() -> None:
    from urllib.parse import urlparse

    from app.core.config import settings

    expected_host = urlparse(settings.REDIS_URL).hostname or "redis"
    assert WorkerSettings.redis_settings.host == expected_host
