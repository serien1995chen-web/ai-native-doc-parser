"""File upload, listing, and detail schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ContentType, FileStatus


class ScreenshotUploadRequest(BaseModel):
    """Base64 screenshot upload payload."""

    image_base64: str


class TextUploadRequest(BaseModel):
    """Text or code paste upload payload."""

    content: str
    type_hint: str | None = Field(default=None, max_length=20)


class FileListParams(BaseModel):
    """List query parameters for files."""

    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)
    status: FileStatus | None = None
    search: str | None = Field(default=None, max_length=200)
    sort: str = Field(
        default="created_at:desc",
        pattern=r"^(created_at|original_name):(asc|desc)$",
    )


class FileResponse(BaseModel):
    """File metadata returned by the API."""

    file_id: uuid.UUID
    original_name: str
    uploaded_type: str
    content_type: ContentType | None = None
    file_size: int | None = None
    status: FileStatus
    mime_type: str | None = None
    identified_type: str | None = None
    identified_confidence: float | None = None
    created_at: datetime
    updated_at: datetime


class FileUploadResponse(BaseModel):
    """Success response for file upload endpoints."""

    file_id: uuid.UUID
    original_name: str
    file_size: int
    status: FileStatus
