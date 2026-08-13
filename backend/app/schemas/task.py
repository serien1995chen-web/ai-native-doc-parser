"""Task management schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import TaskStatus


class TaskResponse(BaseModel):
    """Task metadata returned by the task API."""

    id: uuid.UUID
    file_id: uuid.UUID
    parser_type: str | None = None
    status: TaskStatus
    progress: int
    error_message: str | None = None
    retry_count: int
    created_at: datetime
    completed_at: datetime | None = None


class TaskListParams(BaseModel):
    """Query parameters for the task list endpoint."""

    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)
    status: TaskStatus | None = None
    search: str | None = Field(default=None, max_length=200)
    sort: str = Field(
        default="created_at:desc",
        pattern=r"^(created_at):(asc|desc)$",
    )


class RetryRequest(BaseModel):
    """Empty request body reserved for future retry options."""
