"""File type identification schemas."""

from __future__ import annotations

import uuid

from pydantic import BaseModel


class IdentificationResult(BaseModel):
    """Result produced by the file type identification pipeline."""

    file_id: uuid.UUID
    identified_type: str
    content_type: str | None = None
    identified_confidence: float | None = None
    final_layer: int
    is_final: bool
    details: dict | None = None
