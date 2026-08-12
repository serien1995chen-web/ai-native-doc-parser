"""Application exceptions and FastAPI exception handlers."""

from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from app.schemas.common import ErrorCode

logger = logging.getLogger(__name__)


class AppException(Exception):
    """Application-level error with a stable API error code."""

    def __init__(
        self,
        code: ErrorCode,
        message: str | None = None,
        detail: str | None = None,
    ) -> None:
        self.status_code = code.status_code
        self.code = code.value
        self.message = message or code.value
        self.detail = detail
        super().__init__(self.message)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Return the structured error body for an AppException."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "detail": exc.detail,
            }
        },
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a generic 500 response without leaking internal details."""
    logger.exception("Unhandled exception during request")
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": ErrorCode.INTERNAL_ERROR.value,
                "message": "Internal server error",
                "detail": None,
            }
        },
    )
