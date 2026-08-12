"""Top-level API router."""

from fastapi import APIRouter

from app.api.v1.files import router as files_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(files_router)
