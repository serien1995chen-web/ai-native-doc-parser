"""Shared enums and response schemas used across API modules."""

from __future__ import annotations

from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class TaskStatus(str, Enum):
    """Parse task lifecycle status."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class FileStatus(str, Enum):
    """Uploaded file lifecycle status."""

    UPLOADED = "uploaded"
    IDENTIFYING = "identifying"
    PARSING = "parsing"
    COMPLETED = "completed"
    FAILED = "failed"


class ContentType(str, Enum):
    """User-facing content category."""

    FILE = "file"
    IMAGE = "image"
    FORMULA = "formula"
    TABLE = "table"
    TEXT_BLOCK = "text_block"
    CODE = "code"


class ErrorCode(str, Enum):
    """Stable application error codes."""

    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    PARSER_FAILED = "PARSER_FAILED"
    GPU_UNAVAILABLE = "GPU_UNAVAILABLE"
    TASK_CANCELLED = "TASK_CANCELLED"
    FILE_DUPLICATE = "FILE_DUPLICATE"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    CONVERTER_UNAVAILABLE = "CONVERTER_UNAVAILABLE"

    @property
    def status_code(self) -> int:
        """Return the HTTP status code associated with the error."""
        return {
            ErrorCode.FILE_NOT_FOUND: 404,
            ErrorCode.FILE_TOO_LARGE: 413,
            ErrorCode.UNSUPPORTED_FORMAT: 400,
            ErrorCode.PARSER_FAILED: 500,
            ErrorCode.GPU_UNAVAILABLE: 503,
            ErrorCode.TASK_CANCELLED: 200,
            ErrorCode.FILE_DUPLICATE: 409,
            ErrorCode.UNAUTHORIZED: 401,
            ErrorCode.FORBIDDEN: 403,
            ErrorCode.INTERNAL_ERROR: 500,
            ErrorCode.CONVERTER_UNAVAILABLE: 503,
        }[self]


class APIError(BaseModel):
    """Structured error body returned to API clients."""

    code: str
    message: str
    detail: str | None = None


class APIResponse(BaseModel, Generic[T]):
    """Uniform success/error envelope for API responses."""

    success: bool
    data: T | None = None
    error: APIError | None = None


class PaginatedResponse(BaseModel, Generic[T]):
    """Uniform paginated list response."""

    items: list[T]
    total: int
    page: int
    limit: int
