"""Integration tests for the task management API."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user_id, get_db
from app.api.v1.tasks import get_task_service
from app.core.exceptions import AppException
from app.main import create_app
from app.schemas.common import ErrorCode, PaginatedResponse, TaskStatus
from app.schemas.task import TaskResponse


def _task(status: TaskStatus = TaskStatus.QUEUED) -> TaskResponse:
    now = datetime.now(timezone.utc)
    return TaskResponse(
        id=uuid.uuid4(),
        file_id=uuid.uuid4(),
        parser_type="txt",
        status=status,
        progress=0,
        retry_count=0,
        created_at=now,
        completed_at=None,
    )


class FakeTaskService:
    """Stand-in task service for API integration tests."""

    def __init__(
        self,
        task: TaskResponse,
        list_result: PaginatedResponse[TaskResponse] | None = None,
        fail_not_found: bool = False,
        fail_cancel: bool = False,
    ) -> None:
        self.task = task
        self.list_result = list_result
        self.fail_not_found = fail_not_found
        self.fail_cancel = fail_cancel
        self.retry_called = False
        self.cancel_called = False

    async def list_tasks(
        self,
        db: Any,
        user_id: uuid.UUID,
        params: Any,
    ) -> PaginatedResponse[TaskResponse]:
        return self.list_result

    async def get_task(
        self,
        db: Any,
        user_id: uuid.UUID,
        task_id: uuid.UUID,
    ) -> TaskResponse:
        if self.fail_not_found:
            raise AppException(ErrorCode.FILE_NOT_FOUND, "Task not found")
        return self.task

    async def retry_task(
        self,
        db: Any,
        user_id: uuid.UUID,
        task_id: uuid.UUID,
    ) -> TaskResponse:
        self.retry_called = True
        return self.task

    async def cancel_task(
        self,
        db: Any,
        user_id: uuid.UUID,
        task_id: uuid.UUID,
    ) -> TaskResponse:
        self.cancel_called = True
        if self.fail_cancel:
            raise AppException(
                ErrorCode.PARSER_FAILED,
                "Only queued tasks can be cancelled",
            )
        return self.task


def _override_app(
    service: FakeTaskService,
    user_id: uuid.UUID,
) -> tuple[Any, AsyncMock]:
    app = create_app()
    db = AsyncMock()

    async def override_get_db() -> Any:
        yield db

    async def override_get_user_id() -> uuid.UUID:
        return user_id

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_id] = override_get_user_id
    app.dependency_overrides[get_task_service] = lambda: service
    return app, db


async def _client(app: Any) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_list_tasks_success() -> None:
    task = _task()
    result = PaginatedResponse(
        items=[task],
        total=1,
        page=1,
        limit=20,
    )
    service = FakeTaskService(task, list_result=result)
    app, _ = _override_app(service, uuid.uuid4())

    async with await _client(app) as client:
        response = await client.get("/api/v1/tasks")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["id"] == str(task.id)


@pytest.mark.asyncio
async def test_get_task_success() -> None:
    task = _task()
    app, _ = _override_app(FakeTaskService(task), uuid.uuid4())

    async with await _client(app) as client:
        response = await client.get(f"/api/v1/tasks/{task.id}")

    assert response.status_code == 200
    assert response.json()["data"]["id"] == str(task.id)


@pytest.mark.asyncio
async def test_retry_task_success() -> None:
    task = _task(status=TaskStatus.FAILED)
    service = FakeTaskService(task)
    app, _ = _override_app(service, uuid.uuid4())

    async with await _client(app) as client:
        response = await client.post(f"/api/v1/tasks/{task.id}/retry")

    assert response.status_code == 200
    assert service.retry_called is True
    assert response.json()["data"]["status"] == "failed"


@pytest.mark.asyncio
async def test_cancel_task_success() -> None:
    task = _task()
    service = FakeTaskService(task)
    app, _ = _override_app(service, uuid.uuid4())

    async with await _client(app) as client:
        response = await client.post(f"/api/v1/tasks/{task.id}/cancel")

    assert response.status_code == 200
    assert service.cancel_called is True
    assert response.json()["data"]["status"] == "queued"


@pytest.mark.asyncio
async def test_tasks_require_auth() -> None:
    app = create_app()

    async with await _client(app) as client:
        response = await client.get("/api/v1/tasks")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_get_task_not_found() -> None:
    task = _task()
    service = FakeTaskService(task, fail_not_found=True)
    app, _ = _override_app(service, uuid.uuid4())

    async with await _client(app) as client:
        response = await client.get(f"/api/v1/tasks/{task.id}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "FILE_NOT_FOUND"


@pytest.mark.asyncio
async def test_cancel_non_queued_task_returns_parser_failed() -> None:
    task = _task(status=TaskStatus.PROCESSING)
    service = FakeTaskService(task, fail_cancel=True)
    app, _ = _override_app(service, uuid.uuid4())

    async with await _client(app) as client:
        response = await client.post(f"/api/v1/tasks/{task.id}/cancel")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "PARSER_FAILED"
