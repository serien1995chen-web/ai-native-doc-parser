"""Task management service."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select

from app.core.exceptions import AppException
from app.models import File, ParseTask
from app.schemas.common import (
    ErrorCode,
    FileStatus,
    PaginatedResponse,
    TaskStatus,
)
from app.schemas.task import TaskListParams, TaskResponse
from app.services.parser_router import ParserRouter
from app.services.storage import LocalStorageService

MAX_RETRY_COUNT = 3


def _task_to_response(task: ParseTask) -> TaskResponse:
    """Convert a task ORM row into the API response model."""
    return TaskResponse(
        id=task.id,
        file_id=task.file_id,
        parser_type=task.parser_type,
        status=TaskStatus(task.status),
        progress=task.progress,
        error_message=task.error_message,
        retry_count=task.retry_count,
        created_at=task.created_at,
        completed_at=task.completed_at,
    )


class TaskService:
    """Query and mutate parse tasks owned by the current user."""

    def __init__(self, parser_router: ParserRouter | None = None) -> None:
        self.parser_router = parser_router or ParserRouter(
            storage=LocalStorageService()
        )

    async def list_tasks(
        self,
        db: Any,
        user_id: uuid.UUID,
        params: TaskListParams,
    ) -> PaginatedResponse[TaskResponse]:
        """Return a paginated task list with filters and sorting."""
        filters = [ParseTask.user_id == user_id]
        count_filters = [ParseTask.user_id == user_id]
        if params.status is not None:
            filters.append(ParseTask.status == params.status.value)
            count_filters.append(ParseTask.status == params.status.value)
        if params.search:
            pattern = f"%{params.search}%"
            filters.append(File.original_name.ilike(pattern))
            count_filters.append(File.original_name.ilike(pattern))

        _, sort_direction = params.sort.split(":")
        if sort_direction == "desc":
            order = ParseTask.created_at.desc()
        else:
            order = ParseTask.created_at.asc()
        offset = (params.page - 1) * params.limit
        query = (
            select(ParseTask)
            .join(File, ParseTask.file_id == File.id)
            .where(*filters)
            .order_by(order)
            .offset(offset)
            .limit(params.limit)
        )
        result = await db.execute(query)
        rows = list(result.scalars().all())

        count_result = await db.execute(
            select(func.count())
            .select_from(ParseTask)
            .join(File, ParseTask.file_id == File.id)
            .where(*count_filters)
        )
        total = count_result.scalar_one()
        return PaginatedResponse(
            items=[_task_to_response(task) for task in rows],
            total=total,
            page=params.page,
            limit=params.limit,
        )

    async def get_task(
        self,
        db: Any,
        user_id: uuid.UUID,
        task_id: uuid.UUID,
    ) -> TaskResponse:
        """Return one task owned by the current user."""
        task = await self._load_owned_task(db, user_id, task_id)
        return _task_to_response(task)

    async def retry_task(
        self,
        db: Any,
        user_id: uuid.UUID,
        task_id: uuid.UUID,
    ) -> TaskResponse:
        """Retry a failed task through its original parser path.

        retry_count is the total retry count shared by manual retries and
        worker automatic retries. A manual retry increments it once before
        rerunning; a later worker failure increments it again.
        """
        task = await self._load_owned_task(
            db,
            user_id,
            task_id,
            for_update=True,
        )
        if task.status != TaskStatus.FAILED.value:
            raise AppException(
                ErrorCode.TASK_STATE_CONFLICT,
                "Only failed tasks can be retried",
            )
        if (task.retry_count or 0) >= MAX_RETRY_COUNT:
            raise AppException(
                ErrorCode.TASK_STATE_CONFLICT,
                "Task retry limit reached",
            )

        task.retry_count = (task.retry_count or 0) + 1
        task.status = TaskStatus.QUEUED.value
        task.progress = 0
        task.error_message = None
        task.error_details = None
        await db.commit()

        file = await self._load_file(db, task.file_id)
        identified_type = task.parser_type or file.identified_type or ""
        await self.parser_router.rerun_task(
            db,
            task,
            file,
            identified_type,
        )
        return _task_to_response(task)

    async def cancel_task(
        self,
        db: Any,
        user_id: uuid.UUID,
        task_id: uuid.UUID,
    ) -> TaskResponse:
        """Cancel a queued task."""
        task = await self._load_owned_task(
            db,
            user_id,
            task_id,
            for_update=True,
        )
        if task.status != TaskStatus.QUEUED.value:
            raise AppException(
                ErrorCode.TASK_STATE_CONFLICT,
                "Only queued tasks can be cancelled",
            )
        file = await self._load_file(db, task.file_id)
        task.status = TaskStatus.CANCELLED.value
        file.status = FileStatus.FAILED.value
        file.error_message = "Task cancelled"
        await db.commit()
        return _task_to_response(task)

    async def _load_owned_task(
        self,
        db: Any,
        user_id: uuid.UUID,
        task_id: uuid.UUID,
        for_update: bool = False,
    ) -> ParseTask:
        statement = select(ParseTask).where(
            ParseTask.id == task_id,
            ParseTask.user_id == user_id,
        )
        if for_update:
            statement = statement.with_for_update()
        result = await db.execute(statement)
        task = result.scalar_one_or_none()
        if task is None:
            raise AppException(ErrorCode.FILE_NOT_FOUND, "Task not found")
        return task

    async def _load_file(self, db: Any, file_id: uuid.UUID) -> File:
        result = await db.execute(select(File).where(File.id == file_id))
        file = result.scalar_one_or_none()
        if file is None:
            raise AppException(ErrorCode.FILE_NOT_FOUND, "File not found")
        return file
