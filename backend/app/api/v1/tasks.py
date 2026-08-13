"""Task management endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user_id, get_db
from app.schemas.common import APIResponse, PaginatedResponse, TaskStatus
from app.schemas.task import RetryRequest, TaskListParams, TaskResponse
from app.services.task_service import TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])


def get_task_service() -> TaskService:
    """Provide the task service for the current request."""
    return TaskService()


@router.get("", response_model=APIResponse[PaginatedResponse[TaskResponse]])
async def list_tasks(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    status: TaskStatus | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
    sort: str = Query(
        default="created_at:desc",
        pattern=r"^(created_at):(asc|desc)$",
    ),
    db=Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: TaskService = Depends(get_task_service),
) -> APIResponse[PaginatedResponse[TaskResponse]]:
    """Return a paginated task list for the current user."""
    params = TaskListParams(
        page=page,
        limit=limit,
        status=status,
        search=search,
        sort=sort,
    )
    result = await service.list_tasks(db, user_id, params)
    return APIResponse(success=True, data=result)


@router.get("/{task_id}", response_model=APIResponse[TaskResponse])
async def get_task(
    task_id: uuid.UUID,
    db=Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: TaskService = Depends(get_task_service),
) -> APIResponse[TaskResponse]:
    """Return one task owned by the current user."""
    result = await service.get_task(db, user_id, task_id)
    return APIResponse(success=True, data=result)


@router.post("/{task_id}/retry", response_model=APIResponse[TaskResponse])
async def retry_task(
    task_id: uuid.UUID,
    payload: RetryRequest | None = None,
    db=Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: TaskService = Depends(get_task_service),
) -> APIResponse[TaskResponse]:
    """Retry a failed task."""
    result = await service.retry_task(db, user_id, task_id)
    return APIResponse(success=True, data=result)


@router.post("/{task_id}/cancel", response_model=APIResponse[TaskResponse])
async def cancel_task(
    task_id: uuid.UUID,
    db=Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: TaskService = Depends(get_task_service),
) -> APIResponse[TaskResponse]:
    """Cancel a queued task."""
    result = await service.cancel_task(db, user_id, task_id)
    return APIResponse(success=True, data=result)
