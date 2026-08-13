"""FastAPI application factory and entry point."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.database import init_db
from app.core.exceptions import (
    AppException,
    app_exception_handler,
    generic_exception_handler,
)
from app.core.logging import setup_logging

APP_TITLE = "AI Native Document Parsing Platform"
APP_VERSION = "1.0.0"

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown lifecycle."""
    setup_logging()
    from app import parsers  # noqa: F401
    try:
        await init_db()
        logger.info("Database connection verified")
    except Exception:
        logger.exception("Database connection verification failed")
        raise
    logger.info("Application startup complete")
    yield
    logger.info("Application shutdown complete")


def _resolve_cors_origins(value: str) -> list[str]:
    """Convert the CORS origins setting into a list of allowed origins."""
    if value == "*":
        return ["*"]
    return [origin.strip() for origin in value.split(",") if origin.strip()]


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    application = FastAPI(title=APP_TITLE, version=APP_VERSION, lifespan=lifespan)
    origins = _resolve_cors_origins(settings.CORS_ORIGINS)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials="*" not in origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(api_router)
    application.add_exception_handler(AppException, app_exception_handler)
    application.add_exception_handler(Exception, generic_exception_handler)

    @application.get("/api/v1/health")
    async def health() -> dict[str, str]:
        """Return the service health status."""
        return {"status": "ok", "version": APP_VERSION}

    return application


app = create_app()
