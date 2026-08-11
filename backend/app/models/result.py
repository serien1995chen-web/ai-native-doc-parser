"""Parse result model."""

from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin


class ParseResult(CreatedAtMixin, Base):
    """Formatted output produced by a parse task."""

    __tablename__ = "parse_results"
    __table_args__ = (
        Index("ix_parse_results_task_id", "task_id"),
        Index("ix_parse_results_file_id", "file_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("parse_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
    )
    output_format: Mapped[str] = mapped_column(String(20), nullable=False)
    output_text: Mapped[str | None] = mapped_column(Text)
    output_path: Mapped[str | None] = mapped_column(String(1000))
    json_data: Mapped[dict | None] = mapped_column(JSONB)
    output_size: Mapped[int | None] = mapped_column(BigInteger)
    processing_time_ms: Mapped[int | None] = mapped_column(BigInteger)
