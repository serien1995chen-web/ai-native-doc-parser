"""Parser protocol contracts for document and image parsers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ParseResult:
    """Unified parser output for downstream formatters."""

    markdown: str
    json_data: dict[str, Any]
    page_count: int | None = None
    processing_time_ms: int | None = None


@dataclass
class ParserInfo:
    """Static metadata describing a parser implementation."""

    name: str
    supported_types: list[str]
    required_gpu: bool
    required_models: list[str]
    version: str


class BaseParser(ABC):
    """Abstract interface every parser implementation must satisfy."""

    @abstractmethod
    def info(self) -> ParserInfo:
        """Return metadata about the parser."""
        ...

    @abstractmethod
    def parse(
        self,
        file_path: str,
        options: dict[str, Any] | None = None,
    ) -> ParseResult:
        """Parse the file at file_path and return a unified ParseResult."""
        ...

    def estimate(self, file_path: str) -> dict[str, int]:
        """Estimate resource consumption for the given file."""
        return {"estimated_seconds": 0, "gpu_memory_mb": 0}
