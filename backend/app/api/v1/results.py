"""Result query and download endpoints."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select

from app.api.deps import get_current_user_id, get_db
from app.core.exceptions import AppException
from app.models import ParseResult as ORMResult
from app.models import ParseTask
from app.schemas.common import APIResponse, ErrorCode
from app.schemas.result import ResultResponse
from app.services.pandoc_converter import PandocConverter

router = APIRouter(prefix="/results", tags=["results"])

_CONTENT_TYPES = {
    "markdown": "text/markdown",
    "json": "application/json",
    "html": "text/html",
    "latex": "application/x-latex",
    "docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
}


def get_pandoc_converter() -> PandocConverter:
    """Provide the Pandoc converter client."""
    return PandocConverter()


async def _owned_task(db, task_id: uuid.UUID, user_id: uuid.UUID) -> ParseTask:
    result = await db.execute(select(ParseTask).where(ParseTask.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise AppException(ErrorCode.FILE_NOT_FOUND, "Result not found")
    if task.user_id != user_id:
        raise AppException(ErrorCode.FORBIDDEN, "Forbidden")
    return task


async def _stored_result(
    db,
    task_id: uuid.UUID,
    output_format: str,
) -> ORMResult:
    result = await db.execute(
        select(ORMResult).where(
            ORMResult.task_id == task_id,
            ORMResult.output_format == output_format,
        )
        .order_by(ORMResult.created_at.desc())
        .limit(1)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise AppException(ErrorCode.FILE_NOT_FOUND, "Result not found")
    return record


@router.get("/{task_id}", response_model=APIResponse[ResultResponse])
async def get_result(
    task_id: uuid.UUID,
    format: Literal["markdown", "json"] = Query(default="markdown", alias="format"),
    db=Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> APIResponse[ResultResponse]:
    """Return a stored Markdown or JSON result."""
    task = await _owned_task(db, task_id, user_id)
    record = await _stored_result(db, task.id, format)
    return APIResponse(
        success=True,
        data=ResultResponse(
            task_id=task.id,
            file_id=task.file_id,
            output_format=record.output_format,
            output_text=record.output_text,
            output_size=record.output_size,
        ),
    )


@router.get("/{task_id}/download")
async def download_result(
    task_id: uuid.UUID,
    format: Literal["markdown", "json", "html", "latex", "docx"] = Query(
        default="markdown",
        alias="format",
    ),
    db=Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
    converter: PandocConverter = Depends(get_pandoc_converter),
) -> Response:
    """Download a result in the requested format."""
    task = await _owned_task(db, task_id, user_id)
    if format in {"markdown", "json"}:
        record = await _stored_result(db, task.id, format)
        content = (record.output_text or "").encode("utf-8")
    else:
        markdown_record = await _stored_result(db, task.id, "markdown")
        content = await converter.convert(markdown_record.output_text or "", format)
    return Response(
        content=content,
        media_type=_CONTENT_TYPES[format],
        headers={"Content-Disposition": f'attachment; filename="result.{format}"'},
    )
