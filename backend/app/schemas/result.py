"""Result query and download schemas."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel


class ResultResponse(BaseModel):
    """Stored parse result metadata and text."""

    task_id: uuid.UUID
    file_id: uuid.UUID
    output_format: str
    output_text: str | None = None
    output_size: int | None = None


class DownloadParams(BaseModel):
    """Download format options."""

    format: Literal["markdown", "json", "html", "latex", "docx"]
