"""Top-level API router."""

from fastapi import APIRouter

from app.api.v1.files import router as files_router
from app.api.v1.results import router as results_router
from app.api.v1.tasks import router as tasks_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(files_router)
api_router.include_router(results_router)
api_router.include_router(tasks_router)
