"""Uploaded file model."""

from __future__ import annotations

import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class File(TimestampMixin, Base):
    """File metadata for uploaded and pasted content."""

    __tablename__ = "files"
    __table_args__ = (
        Index("ix_files_user_id", "user_id"),
        Index("ix_files_status", "status"),
        Index("ix_files_content_type", "content_type"),
        Index("ix_files_created_at_desc", text("created_at DESC")),
        Index(
            "ix_files_original_name_trgm",
            "original_name",
            postgresql_using="gin",
            postgresql_ops={"original_name": "gin_trgm_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    original_name: Mapped[str] = mapped_column(String(500), nullable=False)
    uploaded_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_content: Mapped[str | None] = mapped_column(Text)
    type_hint: Mapped[str | None] = mapped_column(String(20))
    stored_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    file_hash: Mapped[str | None] = mapped_column(String(64))
    identified_type: Mapped[str | None] = mapped_column(String(50))
    content_type: Mapped[str | None] = mapped_column(String(30))
    identified_confidence: Mapped[float | None] = mapped_column(Float)
    mime_type: Mapped[str | None] = mapped_column(String(200))
    is_suspicious: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'uploaded'"),
    )
    error_message: Mapped[str | None] = mapped_column(Text)
