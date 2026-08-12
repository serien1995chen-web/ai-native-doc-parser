"""Password hashing, JWT-compatible token helpers, and API key verification."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from app.core.config import settings
from app.core.exceptions import AppException
from app.schemas.common import ErrorCode

PBKDF2_ALGORITHM = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 600_000


def _b64url_encode(data: bytes) -> str:
    """Encode bytes as URL-safe base64 without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    """Decode URL-safe base64, restoring padding when needed."""
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(password: str) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256 and a random salt."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return (
        f"{PBKDF2_ALGORITHM}${PBKDF2_ITERATIONS}"
        f"${_b64url_encode(salt)}${_b64url_encode(digest)}"
    )


def verify_password(password: str, stored: str) -> bool:
    """Verify a password against a stored PBKDF2 hash."""
    try:
        algorithm, iterations_raw, salt_b64, hash_b64 = stored.split("$")
        if algorithm != PBKDF2_ALGORITHM:
            return False
        iterations = int(iterations_raw)
        salt = _b64url_decode(salt_b64)
        expected = _b64url_decode(hash_b64)
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, binascii.Error):
        return False


def _sign_jwt(payload: dict[str, Any]) -> str:
    """Build a JWT-compatible HS256 token using the standard library."""
    header = {"alg": "HS256", "typ": "JWT"}
    encoded_header = _b64url_encode(
        json.dumps(header, separators=(",", ":")).encode("utf-8")
    )
    encoded_payload = _b64url_encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    )
    signing_input = f"{encoded_header}.{encoded_payload}".encode("utf-8")
    signature = _b64url_encode(
        hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            signing_input,
            hashlib.sha256,
        ).digest()
    )
    return f"{encoded_header}.{encoded_payload}.{signature}"


def create_access_token(subject: str) -> str:
    """Create a signed access token for a subject."""
    now = int(time.time())
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + settings.JWT_EXPIRATION_SECONDS,
    }
    return _sign_jwt(payload)


def verify_token(token: str) -> dict[str, Any]:
    """Verify a token signature and expiration, returning its payload."""
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
        header = json.loads(_b64url_decode(header_b64))
        payload = json.loads(_b64url_decode(payload_b64))
        signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
        expected = hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            signing_input,
            hashlib.sha256,
        ).digest()
        actual = _b64url_decode(signature_b64)
        if not hmac.compare_digest(actual, expected):
            raise ValueError("invalid signature")
        if header.get("alg") != "HS256":
            raise ValueError("invalid algorithm")
        if int(payload["exp"]) <= int(time.time()):
            raise ValueError("token expired")
        return payload
    except (ValueError, KeyError, TypeError, binascii.Error, UnicodeDecodeError):
        raise AppException(ErrorCode.UNAUTHORIZED, "Invalid or expired token") from None


def verify_api_key(api_key: str) -> bool:
    """Check an API key with a constant-time comparison."""
    return hmac.compare_digest(api_key, settings.API_KEY)
