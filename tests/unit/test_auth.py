"""Unit tests for API authentication and exception handling."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from unittest.mock import patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.deps import AuthIdentity, get_current_user
from app.core.config import settings
from app.core.exceptions import (
    AppException,
    app_exception_handler,
    generic_exception_handler,
)
from app.core.security import (
    create_access_token,
    hash_password,
    verify_api_key,
    verify_password,
    verify_token,
)
from app.schemas.common import ErrorCode


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _raw_token(payload: object, header: object | None = None) -> str:
    jwt_header = header if header is not None else {"alg": "HS256", "typ": "JWT"}
    encoded_header = _b64url(json.dumps(jwt_header).encode())
    body = _b64url(json.dumps(payload).encode())
    signing_input = f"{encoded_header}.{body}".encode()
    signature = _b64url(
        hmac.new(
            settings.SECRET_KEY.encode(),
            signing_input,
            hashlib.sha256,
        ).digest()
    )
    return f"{encoded_header}.{body}.{signature}"


def _build_test_app() -> TestClient:
    app = FastAPI()
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)

    @app.get("/protected")
    async def protected(user: AuthIdentity = Depends(get_current_user)) -> dict[str, str]:
        return {"user": user.subject}

    return TestClient(app)


def test_password_hash_roundtrip_and_random_salt() -> None:
    stored = hash_password("correct horse")
    assert verify_password("correct horse", stored)
    assert stored != hash_password("correct horse")


def test_wrong_password_fails() -> None:
    stored = hash_password("secret")
    assert not verify_password("wrong", stored)


def test_empty_and_long_passwords() -> None:
    empty_stored = hash_password("")
    assert verify_password("", empty_stored)
    long_password = "x" * 4096
    assert verify_password(long_password, hash_password(long_password))


def test_malformed_stored_hash_fails() -> None:
    assert not verify_password("secret", "not-a-hash")
    assert not verify_password("secret", "pbkdf2_sha256$abc$bad$hash")


def test_create_and_verify_token_payload() -> None:
    token = create_access_token("user-123")
    payload = verify_token(token)
    assert payload["sub"] == "user-123"
    assert payload["exp"] - payload["iat"] == settings.JWT_EXPIRATION_SECONDS


def test_expired_token_raises_unauthorized() -> None:
    now = int(time.time())
    token = _raw_token({"sub": "user", "iat": now - 7200, "exp": now - 3600})
    with pytest.raises(AppException) as exc:
        verify_token(token)
    assert exc.value.code == ErrorCode.UNAUTHORIZED.value


def test_token_exp_equal_now_raises() -> None:
    now = int(time.time())
    token = _raw_token({"sub": "user", "iat": now - 3600, "exp": now})
    with patch("app.core.security.time.time", return_value=now):
        with pytest.raises(AppException) as exc:
            verify_token(token)
    assert exc.value.code == ErrorCode.UNAUTHORIZED.value


def test_tampered_signature_raises() -> None:
    token = create_access_token("user")
    header, payload, signature = token.split(".")
    new_signature = ("A" if signature[0] != "A" else "B") + signature[1:]
    with pytest.raises(AppException):
        verify_token(f"{header}.{payload}.{new_signature}")


def test_tampered_payload_raises() -> None:
    token = create_access_token("user")
    header, _, signature = token.split(".")
    new_payload = _b64url(json.dumps({"sub": "attacker"}).encode())
    with pytest.raises(AppException):
        verify_token(f"{header}.{new_payload}.{signature}")


def test_invalid_token_formats_raise() -> None:
    for bad_token in ("", "not-a-token", "a.b", "a.b.c.d"):
        with pytest.raises(AppException):
            verify_token(bad_token)


def test_token_without_sub_raises_unauthorized() -> None:
    now = int(time.time())
    token = _raw_token({"iat": now, "exp": now + 3600})
    with pytest.raises(AppException) as exc:
        verify_token(token)
    assert exc.value.code == ErrorCode.UNAUTHORIZED.value


def test_token_with_null_sub_raises_unauthorized() -> None:
    now = int(time.time())
    token = _raw_token({"sub": None, "iat": now, "exp": now + 3600})
    with pytest.raises(AppException):
        verify_token(token)


def test_token_with_empty_sub_raises_unauthorized() -> None:
    now = int(time.time())
    token = _raw_token({"sub": "", "iat": now, "exp": now + 3600})
    with pytest.raises(AppException):
        verify_token(token)


def test_token_with_non_string_sub_raises_unauthorized() -> None:
    now = int(time.time())
    token = _raw_token({"sub": 12345, "iat": now, "exp": now + 3600})
    with pytest.raises(AppException):
        verify_token(token)


def test_token_with_missing_typ_raises_unauthorized() -> None:
    now = int(time.time())
    token = _raw_token(
        {"sub": "user", "iat": now, "exp": now + 3600},
        header={"alg": "HS256"},
    )
    with pytest.raises(AppException):
        verify_token(token)


def test_token_with_wrong_typ_raises_unauthorized() -> None:
    now = int(time.time())
    token = _raw_token(
        {"sub": "user", "iat": now, "exp": now + 3600},
        header={"alg": "HS256", "typ": "at+jwt"},
    )
    with pytest.raises(AppException):
        verify_token(token)


def test_token_with_non_object_header_raises_unauthorized() -> None:
    now = int(time.time())
    token = _raw_token(
        {"sub": "user", "iat": now, "exp": now + 3600},
        header=["not", "object"],
    )
    with pytest.raises(AppException):
        verify_token(token)


def test_token_with_non_object_payload_raises_unauthorized() -> None:
    token = _raw_token(["not", "object"])
    with pytest.raises(AppException):
        verify_token(token)


def test_api_key_verification() -> None:
    assert verify_api_key(settings.API_KEY)
    assert not verify_api_key("wrong-key")
    assert not verify_api_key(settings.API_KEY.upper())
    assert not verify_api_key("你好")


def test_protected_route_without_credentials_returns_401() -> None:
    response = _build_test_app().get("/protected")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_protected_route_with_jwt() -> None:
    token = create_access_token("user-123")
    response = _build_test_app().get(
        "/protected",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json() == {"user": "user-123"}


def test_protected_route_with_api_key() -> None:
    response = _build_test_app().get(
        "/protected",
        headers={"Authorization": f"Bearer {settings.API_KEY}"},
    )
    assert response.status_code == 200
    assert response.json() == {"user": "api-key"}


def test_protected_route_rejects_non_bearer_header() -> None:
    response = _build_test_app().get(
        "/protected",
        headers={"Authorization": "Basic abc"},
    )
    assert response.status_code == 401


def test_protected_route_rejects_empty_token() -> None:
    response = _build_test_app().get(
        "/protected",
        headers={"Authorization": "Bearer "},
    )
    assert response.status_code == 401


def test_protected_route_rejects_non_ascii_token() -> None:
    response = _build_test_app().get(
        "/protected",
        headers={"Authorization": b"Bearer \xe4\xbd\xa0\xe5\xa5\xbd"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_app_exception_handler_returns_structured_body() -> None:
    app = FastAPI()
    app.add_exception_handler(AppException, app_exception_handler)

    @app.get("/forbidden")
    async def forbidden() -> None:
        raise AppException(ErrorCode.FORBIDDEN, "No permission", "missing role")

    response = TestClient(app).get("/forbidden")
    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "FORBIDDEN",
            "message": "No permission",
            "detail": "missing role",
        }
    }


def test_generic_exception_handler_returns_internal_error() -> None:
    app = FastAPI()
    app.add_exception_handler(Exception, generic_exception_handler)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret detail")

    response = TestClient(app, raise_server_exceptions=False).get("/boom")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "secret detail" not in body["error"]["message"]
