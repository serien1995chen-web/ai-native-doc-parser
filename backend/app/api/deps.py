"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.security import verify_api_key, verify_token
from app.schemas.common import ErrorCode

bearer_scheme = HTTPBearer(auto_error=False)

__all__ = ["get_db", "get_current_user"]


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    """Resolve the current user from a JWT or fall back to the API key."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppException(ErrorCode.UNAUTHORIZED, "Missing or invalid authorization header")
    token = credentials.credentials
    try:
        payload = verify_token(token)
        return str(payload["sub"])
    except AppException:
        if verify_api_key(token):
            return "api-key"
        raise
