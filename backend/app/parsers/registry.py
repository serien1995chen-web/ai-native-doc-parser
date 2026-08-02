"""Parser registry mapping file types to parser instances."""

from __future__ import annotations

from typing import ClassVar

from app.parsers.base import BaseParser, ParserInfo


class ParserRegistry:
    """Class-level registry shared across the application."""

    _parsers: ClassVar[dict[str, BaseParser]] = {}

    @classmethod
    def register(cls, parser: BaseParser) -> None:
        """Register a parser for every supported file type."""
        info = parser.info()
        for file_type in info.supported_types:
            cls._parsers[file_type] = parser

    @classmethod
    def get_parser(cls, file_type: str) -> BaseParser | None:
        """Return the parser registered for file_type, or None."""
        return cls._parsers.get(file_type)

    @classmethod
    def list_parsers(cls) -> list[ParserInfo]:
        """Return deduplicated metadata for registered parser instances."""
        unique_parsers = set(cls._parsers.values())
        return [parser.info() for parser in unique_parsers]
