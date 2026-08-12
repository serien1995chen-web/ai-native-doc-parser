"""Plain text and Markdown parser."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

from app.parsers.base import BaseParser, ParseResult, ParserInfo
from app.parsers.registry import ParserRegistry

SCHEMA_VERSION = "1.0"


class TextParser(BaseParser):
    """Parse text and Markdown files into unified document blocks."""

    def info(self) -> ParserInfo:
        return ParserInfo(
            name="text_parser",
            supported_types=["txt", "md", "text"],
            required_gpu=False,
            required_models=[],
            version="1.0.0",
        )

    def parse(
        self,
        file_path: str,
        options: dict[str, Any] | None = None,
    ) -> ParseResult:
        started = perf_counter()
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(file_path)

        content = path.read_bytes().decode("utf-8", errors="replace")
        file_type = "md" if path.suffix.lower() == ".md" else "txt"
        blocks: list[dict[str, Any]] = [
            {"type": "paragraph", "text": content, "page": 1}
        ]

        processing_time_ms = round((perf_counter() - started) * 1000, 3)
        json_data = {
            "schema_version": SCHEMA_VERSION,
            "file_type": file_type,
            "page_count": 1,
            "blocks": blocks,
            "meta": {
                "parser": "text_parser",
                "processing_time_ms": processing_time_ms,
            },
        }
        return ParseResult(
            markdown="",
            json_data=json_data,
            page_count=1,
            processing_time_ms=processing_time_ms,
        )


ParserRegistry.register(TextParser())
