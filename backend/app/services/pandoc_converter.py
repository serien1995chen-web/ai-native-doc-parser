"""Pandoc HTTP converter client."""

from __future__ import annotations

import httpx

from app.core.exceptions import AppException
from app.schemas.common import ErrorCode

DEFAULT_PANDOC_URL = "http://tools:8200"


class PandocConverter:
    """Convert Markdown to HTML/LaTeX/DOCX through the tools service."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or DEFAULT_PANDOC_URL

    async def convert(self, markdown: str, target_format: str) -> bytes:
        if target_format in {"markdown", "json"}:
            return markdown.encode("utf-8")
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/convert",
                    json={"markdown": markdown, "format": target_format},
                )
                response.raise_for_status()
                return response.content
        except Exception as exc:
            raise AppException(
                ErrorCode.CONVERTER_UNAVAILABLE,
                "Converter service unavailable",
                str(exc),
            ) from exc
