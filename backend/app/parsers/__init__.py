"""Public parser contracts and registry."""

from __future__ import annotations

from app.parsers.base import BaseParser, ParseResult, ParserInfo
from app.parsers.registry import ParserRegistry

__all__ = ["BaseParser", "ParseResult", "ParserInfo", "ParserRegistry"]

from app.parsers import implementations  # noqa: F401
