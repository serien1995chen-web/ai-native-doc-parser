"""File upload and management endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile

from app.api.deps import get_current_user_id, get_db
from app.core.config import settings
from app.core.exceptions import AppException
from app.schemas.common import APIResponse, ErrorCode, FileStatus, PaginatedResponse
from app.schemas.file import (
    FileListParams,
    FileResponse,
    FileUploadResponse,
    ScreenshotUploadRequest,
    TextUploadRequest,
)
from app.services.storage import LocalStorageService, StorageService
from app.services.upload import UploadService

router = APIRouter(prefix="/files", tags=["files"])


async def _read_upload(file: UploadFile) -> bytes:
    """Read an upload in chunks, rejecting oversized bodies early."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > settings.MAX_UPLOAD_SIZE:
            raise AppException(ErrorCode.FILE_TOO_LARGE, "File exceeds upload size limit")
        chunks.append(chunk)
    return b"".join(chunks)


def get_storage_service() -> StorageService:
    """Provide the configured local storage service."""
    return LocalStorageService()


def get_upload_service(
    storage: StorageService = Depends(get_storage_service),
) -> UploadService:
    """Provide an UploadService bound to the request storage."""
    return UploadService(storage)


@router.post("/upload", response_model=APIResponse[FileUploadResponse])
async def upload_file(
    file: UploadFile = File(...),
    db=Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: UploadService = Depends(get_upload_service),
) -> APIResponse[FileUploadResponse]:
    """Upload a file through multipart form data."""
    data = await _read_upload(file)
    result = await service.upload_file(
        db,
        user_id,
        file.filename or "",
        file.content_type,
        data,
        content_type="file",
    )
    return APIResponse(success=True, data=result)


@router.post("/upload/screenshot", response_model=APIResponse[FileUploadResponse])
async def upload_screenshot(
    payload: ScreenshotUploadRequest,
    db=Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: UploadService = Depends(get_upload_service),
) -> APIResponse[FileUploadResponse]:
    """Upload a base64 PNG screenshot."""
    result = await service.upload_screenshot(db, user_id, payload.image_base64)
    return APIResponse(success=True, data=result)


@router.post("/upload/text", response_model=APIResponse[FileUploadResponse])
async def upload_text(
    payload: TextUploadRequest,
    db=Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: UploadService = Depends(get_upload_service),
) -> APIResponse[FileUploadResponse]:
    """Upload pasted text or code."""
    result = await service.upload_text(db, user_id, payload.content, payload.type_hint)
    return APIResponse(success=True, data=result)


@router.get("", response_model=APIResponse[PaginatedResponse[FileResponse]])
async def list_files(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    status: FileStatus | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
    sort: str = Query(
        default="created_at:desc",
        pattern=r"^(created_at|original_name):(asc|desc)$",
    ),
    db=Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: UploadService = Depends(get_upload_service),
) -> APIResponse[PaginatedResponse[FileResponse]]:
    """List files owned by the current user."""
    params = FileListParams(page=page, limit=limit, status=status, search=search, sort=sort)
    result = await service.list_files(db, user_id, params)
    return APIResponse(success=True, data=result)


@router.get("/{file_id}", response_model=APIResponse[FileResponse])
async def get_file(
    file_id: uuid.UUID,
    db=Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: UploadService = Depends(get_upload_service),
) -> APIResponse[FileResponse]:
    """Return file details."""
    result = await service.get_file(db, user_id, file_id)
    return APIResponse(success=True, data=result)


@router.delete("/{file_id}", response_model=APIResponse[None])
async def delete_file(
    file_id: uuid.UUID,
    db=Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: UploadService = Depends(get_upload_service),
) -> APIResponse[None]:
    """Delete a file."""
    await service.delete_file(db, user_id, file_id)
    return APIResponse(success=True, data=None)
