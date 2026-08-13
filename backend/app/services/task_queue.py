"""arq task queue helpers."""

from __future__ import annotations

from typing import Any

from arq import ArqRedis

from app.core.config import settings

PARSE_PDF_TASK = "parse_pdf_task"
PARSE_IMAGE_TASK = "parse_image_task"


async def enqueue_job(job_name: str, **kwargs: Any) -> str | None:
    """Enqueue an arq job and close the Redis connection."""
    redis = ArqRedis.from_url(settings.REDIS_URL)
    try:
        job = await redis.enqueue_job(job_name, **kwargs)
        return job.job_id if job is not None else None
    finally:
        await redis.aclose()
