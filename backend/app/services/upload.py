"""Upload orchestration and file metadata persistence."""

from __future__ import annotations

import base64
import binascii
import hashlib
import mimetypes
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from app.core.config import settings
from app.core.exceptions import AppException
from app.models import File
from app.schemas.common import ErrorCode, FileStatus, PaginatedResponse
from app.schemas.file import FileListParams, FileResponse, FileUploadResponse
from app.services.storage import StorageService


def _safe_filename(name: str) -> str:
    """Return a filesystem-safe basename, guarding against path traversal."""
    safe = Path(name).name.strip()
    if not safe:
        return "file"
    return safe[:255]


def _relative_path(file_id: uuid.UUID, name: str) -> str:
    now = datetime.now(timezone.utc)
    return f"{now:%Y/%m}/{file_id}/{_safe_filename(name)}"


def _file_to_response(file: File) -> FileResponse:
    return FileResponse(
        file_id=file.id,
        original_name=file.original_name,
        uploaded_type=file.uploaded_type,
        content_type=file.content_type,
        file_size=file.file_size,
        status=FileStatus(file.status),
        mime_type=file.mime_type,
        created_at=file.created_at,
        updated_at=file.updated_at,
    )


class UploadService:
    """High-level upload, listing, and deletion operations."""

    def __init__(self, storage: StorageService) -> None:
        self.storage = storage

    async def _check_duplicate(self, db: Any, data: bytes) -> str:
        """Compute SHA-256 and reject content already stored globally."""
        file_hash = hashlib.sha256(data).hexdigest()
        result = await db.execute(
            select(File).where(File.file_hash == file_hash).limit(1)
        )
        if result.scalar_one_or_none() is not None:
            raise AppException(
                ErrorCode.FILE_DUPLICATE,
                "A file with the same content already exists",
            )
        return file_hash

    async def upload_file(
        self,
        db: Any,
        user_id: uuid.UUID,
        original_name: str,
        mime_type: str | None,
        data: bytes,
        content_type: str | None = None,
    ) -> FileUploadResponse:
        """Persist an uploaded file and its metadata."""
        if len(data) > settings.MAX_UPLOAD_SIZE:
            raise AppException(ErrorCode.FILE_TOO_LARGE, "File exceeds upload size limit")
        file_hash = await self._check_duplicate(db, data)

        file_id = uuid.uuid4()
        safe_name = _safe_filename(original_name)
        relative_path = _relative_path(file_id, safe_name)
        try:
            await self.storage.save_bytes(relative_path, data)
        except Exception:
            await db.rollback()
            raise
        now = datetime.now(timezone.utc)
        record = File(
            id=file_id,
            user_id=user_id,
            original_name=safe_name,
            uploaded_type="file",
            stored_path=relative_path,
            file_size=len(data),
            file_hash=file_hash,
            content_type=content_type,
            mime_type=mimetypes.guess_type(safe_name)[0] or mime_type,
            status=FileStatus.UPLOADED.value,
            created_at=now,
            updated_at=now,
        )
        db.add(record)
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return FileUploadResponse(
            file_id=file_id,
            original_name=safe_name,
            file_size=len(data),
            status=FileStatus.UPLOADED,
        )

    async def upload_screenshot(
        self,
        db: Any,
        user_id: uuid.UUID,
        image_base64: str,
    ) -> FileUploadResponse:
        """Decode and persist a PNG screenshot paste."""
        prefix = "data:image/png;base64,"
        if not image_base64.startswith(prefix):
            raise AppException(
                ErrorCode.UNSUPPORTED_FORMAT,
                "Only data:image/png;base64 screenshots are supported",
            )
        payload = image_base64.split(",", 1)[1]
        try:
            data = base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError):
            raise AppException(
                ErrorCode.UNSUPPORTED_FORMAT,
                "Invalid base64 screenshot data",
            ) from None
        if not data:
            raise AppException(ErrorCode.UNSUPPORTED_FORMAT, "Screenshot data is empty")
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise AppException(
                ErrorCode.UNSUPPORTED_FORMAT,
                "Screenshot data is not a PNG image",
            )
        return await self.upload_file(
            db,
            user_id,
            "screenshot.png",
            "image/png",
            data,
            content_type="image",
        )

    async def upload_text(
        self,
        db: Any,
        user_id: uuid.UUID,
        content: str,
        type_hint: str | None,
    ) -> FileUploadResponse:
        """Persist a pasted text or code block."""
        if type_hint is not None and type_hint not in {"text", "code"}:
            raise AppException(
                ErrorCode.UNSUPPORTED_FORMAT,
                "type_hint must be text or code",
            )
        data = content.encode("utf-8")
        if len(data) > settings.MAX_UPLOAD_SIZE:
            raise AppException(ErrorCode.FILE_TOO_LARGE, "Text exceeds upload size limit")
        file_hash = await self._check_duplicate(db, data)

        file_id = uuid.uuid4()
        safe_name = f"paste-{file_id}.txt"
        relative_path = _relative_path(file_id, safe_name)
        try:
            await self.storage.save_text(relative_path, content)
        except Exception:
            await db.rollback()
            raise
        content_type = (
            "text_block"
            if type_hint == "text"
            else "code"
            if type_hint == "code"
            else None
        )
        now = datetime.now(timezone.utc)
        record = File(
            id=file_id,
            user_id=user_id,
            original_name=safe_name,
            uploaded_type="text",
            source_content=content,
            type_hint=type_hint,
            stored_path=relative_path,
            file_size=len(data),
            file_hash=file_hash,
            content_type=content_type,
            mime_type="text/plain",
            status=FileStatus.UPLOADED.value,
            created_at=now,
            updated_at=now,
        )
        db.add(record)
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return FileUploadResponse(
            file_id=file_id,
            original_name=safe_name,
            file_size=len(data),
            status=FileStatus.UPLOADED,
        )

    async def list_files(
        self,
        db: Any,
        user_id: uuid.UUID,
        params: FileListParams,
    ) -> PaginatedResponse[FileResponse]:
        """List files with filtering, search, sorting, and pagination."""
        filters = [File.user_id == user_id]
        count_filters = [File.user_id == user_id]
        if params.status is not None:
            filters.append(File.status == params.status.value)
            count_filters.append(File.status == params.status.value)
        if params.search:
            pattern = f"%{params.search}%"
            filters.append(File.original_name.ilike(pattern))
            count_filters.append(File.original_name.ilike(pattern))

        sort_field, sort_direction = params.sort.split(":")
        column = File.created_at if sort_field == "created_at" else File.original_name
        order = column.desc() if sort_direction == "desc" else column.asc()
        offset = (params.page - 1) * params.limit
        query = (
            select(File)
            .where(*filters)
            .order_by(order)
            .offset(offset)
            .limit(params.limit)
        )
        result = await db.execute(query)
        rows = list(result.scalars().all())

        count_result = await db.execute(
            select(func.count()).select_from(File).where(*count_filters)
        )
        total = count_result.scalar_one()
        return PaginatedResponse(
            items=[_file_to_response(file) for file in rows],
            total=total,
            page=params.page,
            limit=params.limit,
        )

    async def get_file(
        self,
        db: Any,
        user_id: uuid.UUID,
        file_id: uuid.UUID,
    ) -> FileResponse:
        """Return one file owned by the current user."""
        result = await db.execute(
            select(File).where(File.id == file_id, File.user_id == user_id)
        )
        file = result.scalar_one_or_none()
        if file is None:
            raise AppException(ErrorCode.FILE_NOT_FOUND, "File not found")
        return _file_to_response(file)

    async def delete_file(
        self,
        db: Any,
        user_id: uuid.UUID,
        file_id: uuid.UUID,
    ) -> None:
        """Delete stored content and metadata for one file."""
        result = await db.execute(
            select(File).where(File.id == file_id, File.user_id == user_id)
        )
        file = result.scalar_one_or_none()
        if file is None:
            raise AppException(ErrorCode.FILE_NOT_FOUND, "File not found")
        await self.storage.delete(file.stored_path)
        await db.delete(file)
        await db.commit()
