"""Source code parser using Pygments language detection."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

from pygments.lexers import get_lexer_for_filename, guess_lexer
from pygments.util import ClassNotFound

from app.parsers.base import BaseParser, ParseResult, ParserInfo
from app.parsers.registry import ParserRegistry

SCHEMA_VERSION = "1.0"

SUPPORTED_TYPES = [
    "code",
    "python",
    "javascript",
    "java",
    "c",
    "cpp",
    "go",
    "rust",
    "json",
    "yaml",
    "xml",
    "sql",
    "shell",
]

PREFERRED_ALIASES = {
    ".py": "python",
    ".js": "javascript",
}


def _lexer_alias(lexer: Any, filename: str) -> str:
    """Return a stable Pygments alias for the detected lexer."""
    aliases = list(getattr(lexer, "aliases", None) or [])
    suffix = Path(filename).suffix.lower()
    if suffix in PREFERRED_ALIASES and PREFERRED_ALIASES[suffix] in aliases:
        return PREFERRED_ALIASES[suffix]
    if aliases:
        return aliases[0]
    return lexer.name.lower()


class CodeParser(BaseParser):
    """Parse source code files into unified document blocks."""

    def info(self) -> ParserInfo:
        return ParserInfo(
            name="code_parser",
            supported_types=SUPPORTED_TYPES,
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
        try:
            lexer = get_lexer_for_filename(path.name)
        except ClassNotFound:
            try:
                lexer = guess_lexer(content)
            except ClassNotFound:
                language = "text"
            else:
                language = _lexer_alias(lexer, path.name)
        else:
            language = _lexer_alias(lexer, path.name)

        blocks: list[dict[str, Any]] = [
            {"type": "code", "language": language, "text": content, "page": 1}
        ]

        processing_time_ms = round((perf_counter() - started) * 1000, 3)
        json_data = {
            "schema_version": SCHEMA_VERSION,
            "file_type": "code",
            "page_count": 1,
            "blocks": blocks,
            "meta": {
                "parser": "code_parser",
                "processing_time_ms": processing_time_ms,
            },
        }
        return ParseResult(
            markdown="",
            json_data=json_data,
            page_count=1,
            processing_time_ms=processing_time_ms,
        )


ParserRegistry.register(CodeParser())
