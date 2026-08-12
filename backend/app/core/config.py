"""Application configuration management."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables and the .env file."""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = "postgresql+asyncpg://docparser:changeme@localhost:5432/docparser"
    REDIS_URL: str = "redis://localhost:6379/0"
    MINIO_ENDPOINT: str = "http://localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MAX_UPLOAD_SIZE: int = 104857600
    UPLOAD_DIR: str = "/data/uploads"
    L1_CONFIDENCE_THRESHOLD: float = 0.95
    L2_CONFIDENCE_THRESHOLD: float = 0.90
    L3_CONFIDENCE_THRESHOLD: float = 0.85
    PANDOC_ENABLED: bool = True
    SECRET_KEY: str = "dev-secret-key-change-me"
    API_KEY: str = "dev-api-key-change-me"
    JWT_EXPIRATION_SECONDS: int = 86400
    CORS_ORIGINS: str = "*"


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    return Settings()


settings = get_settings()
