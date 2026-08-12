"""Shared FastAPI dependencies."""

from __future__ import annotations

import uuid

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.security import verify_api_key, verify_token
from app.models import User
from app.schemas.common import ErrorCode

bearer_scheme = HTTPBearer(auto_error=False)

__all__ = ["get_db", "get_current_user", "get_current_user_id"]


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


async def get_current_user_id(
    db: AsyncSession = Depends(get_db),
    identity: str = Depends(get_current_user),
) -> uuid.UUID:
    """Resolve a user id from JWT subject or the development API key user."""
    if identity == "api-key":
        result = await db.execute(select(User).where(User.username == "api-key"))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                id=uuid.uuid4(),
                username="api-key",
                password_hash="",
                role="user",
                is_active=True,
            )
            db.add(user)
            await db.commit()
        return user.id

    try:
        user_id = uuid.UUID(identity)
    except (ValueError, AttributeError, TypeError):
        raise AppException(ErrorCode.UNAUTHORIZED, "Invalid user identity") from None
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise AppException(ErrorCode.UNAUTHORIZED, "User not found")
    return user.id
