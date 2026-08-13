"""Parser routing: synchronous parsers and arq async tasks."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.core.exceptions import AppException
from app.models import File, ParseTask
from app.parsers import ParserRegistry
from app.schemas.common import ErrorCode, FileStatus
from app.services.storage import LocalStorageService, StorageService
from app.services.output_formatter import UnifiedOutputFormatter
from app.services.task_queue import (
    PARSE_IMAGE_TASK,
    PARSE_PDF_TASK,
    enqueue_job,
)

SYNC_TYPES = {
    "doc",
    "docx",
    "ppt",
    "pptx",
    "xls",
    "xlsx",
    "html",
    "htm",
    "txt",
    "md",
    "text",
    "code",
    "python",
    "javascript",
    "java",
    "c",
    "cpp",
    "go",
    "rust",
    "json",
    "yaml",
    "xml",
    "sql",
    "shell",
}


class ParserRouter:
    """Dispatch files to synchronous parsers or the arq queue."""

    def __init__(self, storage: StorageService | None = None) -> None:
        self.storage = storage or LocalStorageService()

    async def route(
        self,
        db: Any,
        file_id: uuid.UUID,
        identified_type: str,
        user_id: uuid.UUID,
    ) -> None:
        """Route one identified file to the matching parser path."""
        result = await db.execute(select(File).where(File.id == file_id))
        file = result.scalar_one_or_none()
        if file is None:
            raise AppException(ErrorCode.FILE_NOT_FOUND, "File not found")

        if identified_type == "pdf":
            await self._enqueue_async(db, file, user_id, "pdf", PARSE_PDF_TASK)
            return
        if identified_type.startswith("image"):
            await self._enqueue_async(
                db,
                file,
                user_id,
                identified_type,
                PARSE_IMAGE_TASK,
            )
            return
        if identified_type in SYNC_TYPES:
            await self._run_sync(db, file, user_id, identified_type)
            return

        file.status = FileStatus.FAILED.value
        file.error_message = f"Unsupported file type: {identified_type}"
        await db.commit()
        raise AppException(ErrorCode.UNSUPPORTED_FORMAT, "Unsupported file type")

    async def _run_sync(
        self,
        db: Any,
        file: File,
        user_id: uuid.UUID,
        identified_type: str,
    ) -> None:
        parser = ParserRegistry.get_parser(identified_type)
        if parser is None:
            file.status = FileStatus.FAILED.value
            file.error_message = f"Unsupported file type: {identified_type}"
            await db.commit()
            raise AppException(ErrorCode.UNSUPPORTED_FORMAT, "Unsupported file type")

        task = ParseTask(
            id=uuid.uuid4(),
            file_id=file.id,
            user_id=user_id,
            parser_type=identified_type,
            status="queued",
            progress=0,
        )
        db.add(task)
        await db.commit()

        task.status = "processing"
        task.started_at = datetime.now(timezone.utc)
        await db.commit()
        try:
            path = self.storage.resolve_path(file.stored_path)
            parser_result = parser.parse(str(path))
            formatter = UnifiedOutputFormatter()
            formatted = formatter.format_blocks(
                parser_result.json_data.get("blocks", []),
                identified_type,
                parser_result.json_data.get("meta", {}),
            )
            await formatter.persist_parse_results(
                db,
                task.id,
                file.id,
                formatted,
            )
            task.progress = 100
            task.status = FileStatus.COMPLETED.value
            task.completed_at = datetime.now(timezone.utc)
            file.status = FileStatus.COMPLETED.value
            await db.commit()
        except Exception as exc:
            task.status = FileStatus.FAILED.value
            task.error_message = str(exc)
            task.error_details = {"type": type(exc).__name__}
            file.status = FileStatus.FAILED.value
            file.error_message = str(exc)
            await db.commit()
            raise AppException(
                ErrorCode.PARSER_FAILED,
                "Parser failed",
                str(exc),
            ) from exc

    async def _enqueue_async(
        self,
        db: Any,
        file: File,
        user_id: uuid.UUID,
        parser_type: str,
        job_name: str,
    ) -> None:
        task = ParseTask(
            id=uuid.uuid4(),
            file_id=file.id,
            user_id=user_id,
            parser_type=parser_type,
            status="queued",
            progress=0,
        )
        db.add(task)
        await db.commit()
        try:
            await enqueue_job(job_name, file_id=str(file.id))
        except Exception as exc:
            task.status = FileStatus.FAILED.value
            task.error_message = f"Failed to enqueue job: {exc}"
            task.error_details = {"type": type(exc).__name__}
            file.status = FileStatus.FAILED.value
            file.error_message = task.error_message
            await db.commit()
            raise AppException(
                ErrorCode.PARSER_FAILED,
                "Failed to enqueue job",
                str(exc),
            ) from exc
