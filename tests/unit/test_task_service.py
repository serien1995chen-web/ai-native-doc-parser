"""Unit tests for the task management service."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from app.core.exceptions import AppException
from app.models import File, ParseTask
from app.schemas.common import ErrorCode, TaskStatus
from app.schemas.task import TaskListParams
from app.services.task_service import TaskService


class FakeResult:
    """Minimal DB result stub."""

    def __init__(self, rows: list[Any], total: int | None = None) -> None:
        self._rows = rows
        self._total = len(rows) if total is None else total

    def scalar_one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None

    def scalar_one(self) -> int:
        return self._total

    def scalars(self) -> FakeResult:
        return self

    def all(self) -> list[Any]:
        return self._rows


class FakeParserRouter:
    """Stand-in parser router used by task service tests."""

    def __init__(self) -> None:
        self.rerun_calls: list[tuple[Any, Any, str]] = []

    async def rerun_task(
        self,
        db: Any,
        task: ParseTask,
        file: File,
        identified_type: str,
    ) -> None:
        self.rerun_calls.append((task, file, identified_type))


class LockingFakeDB:
    """Fake async session that serializes FOR UPDATE task reads."""

    def __init__(self, task: ParseTask, file: File) -> None:
        self.task = task
        self.file = file
        self.locked = False
        self.release_event = asyncio.Event()
        self.commits = 0

    async def execute(self, statement: Any) -> FakeResult:
        sql = str(
            statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        if "FOR UPDATE" in sql:
            if self.locked:
                await self.release_event.wait()
            self.locked = True
        if "FROM parse_tasks" in sql:
            return FakeResult([self.task])
        if "FROM files" in sql:
            return FakeResult([self.file])
        return FakeResult([])

    async def commit(self) -> None:
        self.commits += 1
        if self.locked:
            self.locked = False
            self.release_event.set()
            self.release_event = asyncio.Event()

    async def rollback(self) -> None:
        if self.locked:
            self.locked = False
            self.release_event.set()
            self.release_event = asyncio.Event()


def _make_file() -> File:
    return File(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        original_name="report.pdf",
        uploaded_type="file",
        stored_path="2026/01/01/report.pdf",
        identified_type="txt",
        status="failed",
    )


def _make_task(
    status: str = "failed",
    parser_type: str | None = "txt",
    retry_count: int = 0,
) -> ParseTask:
    now = datetime.now(timezone.utc)
    return ParseTask(
        id=uuid.uuid4(),
        file_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        parser_type=parser_type,
        status=status,
        progress=0,
        retry_count=retry_count,
        created_at=now,
        updated_at=now,
    )


def _service(router: FakeParserRouter | None = None) -> TaskService:
    return TaskService(parser_router=router or FakeParserRouter())


def _db(*results: FakeResult) -> AsyncMock:
    db = AsyncMock()
    db.execute.side_effect = list(results)
    return db


@pytest.mark.asyncio
async def test_list_tasks_returns_paginated_response() -> None:
    task = _make_task()
    db = _db(FakeResult([task]), FakeResult([], total=1))
    service = _service()

    result = await service.list_tasks(
        db,
        task.user_id,
        TaskListParams(page=1, limit=10),
    )

    assert result.total == 1
    assert len(result.items) == 1
    assert result.items[0].id == task.id


@pytest.mark.asyncio
async def test_get_task_not_found() -> None:
    db = _db(FakeResult([]))
    service = _service()

    with pytest.raises(AppException) as exc:
        await service.get_task(db, uuid.uuid4(), uuid.uuid4())

    assert exc.value.code == ErrorCode.FILE_NOT_FOUND.value


@pytest.mark.asyncio
async def test_retry_task_rejects_non_failed() -> None:
    task = _make_task(status="completed")
    db = _db(FakeResult([task]))
    service = _service()

    with pytest.raises(AppException) as exc:
        await service.retry_task(db, task.user_id, task.id)

    assert exc.value.code == ErrorCode.TASK_STATE_CONFLICT.value


@pytest.mark.asyncio
async def test_retry_task_rejects_retry_limit() -> None:
    task = _make_task(retry_count=3)
    db = _db(FakeResult([task]))
    service = _service()

    with pytest.raises(AppException) as exc:
        await service.retry_task(db, task.user_id, task.id)

    assert exc.value.code == ErrorCode.TASK_STATE_CONFLICT.value


@pytest.mark.asyncio
async def test_retry_task_sync_reruns_existing_task() -> None:
    task = _make_task(parser_type="txt", retry_count=1)
    file = _make_file()
    db = _db(FakeResult([task]), FakeResult([file]))
    router = FakeParserRouter()
    service = _service(router)

    response = await service.retry_task(db, task.user_id, task.id)

    assert task.retry_count == 2
    assert task.status == TaskStatus.QUEUED.value
    assert task.progress == 0
    assert task.error_message is None
    assert task.error_details is None
    assert response.status == TaskStatus.QUEUED
    assert len(router.rerun_calls) == 1
    assert router.rerun_calls[0][0] is task
    assert router.rerun_calls[0][1] is file
    assert router.rerun_calls[0][2] == "txt"


@pytest.mark.asyncio
async def test_retry_task_async_requeues_existing_task() -> None:
    task = _make_task(parser_type="pdf", retry_count=0)
    file = _make_file()
    file.identified_type = "pdf"
    db = _db(FakeResult([task]), FakeResult([file]))
    router = FakeParserRouter()
    service = _service(router)

    response = await service.retry_task(db, task.user_id, task.id)

    assert task.retry_count == 1
    assert response.status == TaskStatus.QUEUED
    assert router.rerun_calls[0][2] == "pdf"


@pytest.mark.asyncio
async def test_cancel_task_queued_succeeds() -> None:
    task = _make_task(status="queued")
    file = _make_file()
    db = _db(FakeResult([task]), FakeResult([file]))
    service = _service()

    response = await service.cancel_task(db, task.user_id, task.id)

    assert task.status == TaskStatus.CANCELLED.value
    assert file.status == "failed"
    assert file.error_message == "Task cancelled"
    assert response.status == TaskStatus.CANCELLED


@pytest.mark.asyncio
async def test_cancel_task_rejects_non_queued() -> None:
    task = _make_task(status="processing")
    db = _db(FakeResult([task]))
    service = _service()

    with pytest.raises(AppException) as exc:
        await service.cancel_task(db, task.user_id, task.id)

    assert exc.value.code == ErrorCode.TASK_STATE_CONFLICT.value


@pytest.mark.asyncio
async def test_retry_task_uses_row_lock() -> None:
    task = _make_task()
    file = _make_file()
    db = _db(FakeResult([task]), FakeResult([file]))
    service = _service()

    await service.retry_task(db, task.user_id, task.id)

    statement = db.execute.call_args_list[0].args[0]
    compiled = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "FOR UPDATE" in compiled


@pytest.mark.asyncio
async def test_concurrent_retry_only_one_succeeds() -> None:
    task = _make_task(parser_type="txt", retry_count=0)
    file = _make_file()
    db = LockingFakeDB(task, file)
    service = _service()

    results = await asyncio.gather(
        service.retry_task(db, task.user_id, task.id),
        service.retry_task(db, task.user_id, task.id),
        return_exceptions=True,
    )

    succeeded = [result for result in results if not isinstance(result, BaseException)]
    conflicts = [
        result
        for result in results
        if isinstance(result, AppException)
        and result.code == ErrorCode.TASK_STATE_CONFLICT.value
    ]
    assert len(succeeded) == 1
    assert len(conflicts) == 1
    assert task.retry_count == 1
    assert task.status == TaskStatus.QUEUED.value


@pytest.mark.asyncio
async def test_cancel_and_retry_race_only_cancel_succeeds() -> None:
    task = _make_task(status="queued")
    file = _make_file()
    db = _db(FakeResult([task]), FakeResult([file]), FakeResult([task]))
    service = _service()

    results = await asyncio.gather(
        service.cancel_task(db, task.user_id, task.id),
        service.retry_task(db, task.user_id, task.id),
        return_exceptions=True,
    )

    successes = [result for result in results if not isinstance(result, BaseException)]
    conflicts = [
        result
        for result in results
        if isinstance(result, AppException)
        and result.code == ErrorCode.TASK_STATE_CONFLICT.value
    ]
    assert len(successes) == 1
    assert len(conflicts) == 1
    assert task.status == TaskStatus.CANCELLED.value
    assert file.status == "failed"
    assert file.error_message == "Task cancelled"


@pytest.mark.asyncio
async def test_cancel_task_updates_file_status() -> None:
    task = _make_task(status="queued")
    file = _make_file()
    db = _db(FakeResult([task]), FakeResult([file]))
    service = _service()

    response = await service.cancel_task(db, task.user_id, task.id)

    assert task.status == TaskStatus.CANCELLED.value
    assert file.status == "failed"
    assert file.error_message == "Task cancelled"
    assert response.status == TaskStatus.CANCELLED
