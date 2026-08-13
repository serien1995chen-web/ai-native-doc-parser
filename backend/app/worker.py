from datetime import datetime, timezone

from arq.connections import RedisSettings
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models import File, ParseTask
from app.parsers import ParserRegistry
from app.services.storage import LocalStorageService
from app.services.task_queue import (
    PARSE_IMAGE_TASK,
    PARSE_PDF_TASK,
    enqueue_job,
)

storage = LocalStorageService()


async def startup(ctx):
    print("worker startup")


async def shutdown(ctx):
    print("worker shutdown")


async def _latest_task(db, file_id):
    result = await db.execute(
        select(ParseTask)
        .where(ParseTask.file_id == file_id)
        .order_by(ParseTask.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _run_worker_task(ctx, file_id, parser_type, job_name):
    async with AsyncSessionLocal() as db:
        file_result = await db.execute(select(File).where(File.id == file_id))
        file = file_result.scalar_one_or_none()
        task = await _latest_task(db, file_id)
        if file is None or task is None:
            return

        task.status = "processing"
        task.started_at = datetime.now(timezone.utc)
        await db.commit()

        parser = ParserRegistry.get_parser(parser_type)
        if parser is None:
            task.status = "failed"
            task.error_message = f"Unsupported parser type: {parser_type}"
            task.error_details = {"type": "UNSUPPORTED_FORMAT"}
            file.status = "failed"
            file.error_message = task.error_message
            await db.commit()
            return

        try:
            path = storage.resolve_path(file.stored_path)
            parser.parse(str(path))
            task.progress = 100
            task.status = "completed"
            task.completed_at = datetime.now(timezone.utc)
            file.status = "completed"
            await db.commit()
        except Exception as exc:
            task.retry_count = (task.retry_count or 0) + 1
            task.error_message = str(exc)
            task.error_details = {"type": type(exc).__name__}
            if task.retry_count < 3:
                task.status = "queued"
                await db.commit()
                try:
                    await enqueue_job(
                        job_name,
                        file_id=str(file_id),
                        _defer_by=2 ** task.retry_count,
                    )
                except Exception:
                    task.status = "failed"
                    file.status = "failed"
                    await db.commit()
            else:
                task.status = "failed"
                file.status = "failed"
                await db.commit()


async def parse_pdf_task(ctx, file_id):
    await _run_worker_task(ctx, file_id, "pdf", PARSE_PDF_TASK)


async def parse_image_task(ctx, file_id):
    await _run_worker_task(ctx, file_id, "image", PARSE_IMAGE_TASK)


class WorkerSettings:
    functions = [parse_pdf_task, parse_image_task]

    redis_settings = RedisSettings(
        host="redis",
        port=6379,
    )

    on_startup = startup
    on_shutdown = shutdown
