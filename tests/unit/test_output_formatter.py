"""Unit tests for the unified output formatter."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.parsers.base import ParseResult as ParserParseResult
from app.services.output_formatter import UnifiedOutputFormatter


class FakeDB:
    """In-memory session stub for persistence tests."""

    def __init__(self) -> None:
        self.added: list[Any] = []
        self.commits = 0

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commits += 1


def _parse_result(blocks: list[dict[str, Any]]) -> ParserParseResult:
    return ParserParseResult(
        markdown="",
        json_data={"blocks": blocks, "meta": {"parser": "stub"}},
    )


def test_blocks_to_markdown_rules() -> None:
    blocks = [
        {"type": "heading", "level": 2, "text": "Title"},
        {"type": "paragraph", "text": "Hello"},
        {
            "type": "table",
            "rows": [["a", "b"], ["1", "2"]],
        },
        {"type": "image", "src": "x.png", "caption": "cap"},
        {"type": "formula", "text": "x^2"},
        {"type": "code", "language": "python", "text": "print(1)"},
    ]
    markdown = UnifiedOutputFormatter.to_markdown(_parse_result(blocks))

    assert "## Title" in markdown
    assert "Hello" in markdown
    assert "| a | b |" in markdown
    assert "| --- | --- |" in markdown
    assert "![cap](x.png)" in markdown
    assert "$$x^2$$" in markdown
    assert "```python" in markdown
    assert "print(1)" in markdown


def test_empty_blocks_produce_empty_markdown() -> None:
    assert UnifiedOutputFormatter.to_markdown(_parse_result([])) == ""


def test_to_json_returns_json_data() -> None:
    result = _parse_result([{"type": "paragraph", "text": "hi"}])
    assert UnifiedOutputFormatter.to_json(result)["blocks"][0]["text"] == "hi"


def test_table_pads_short_rows() -> None:
    blocks = [{"type": "table", "rows": [["a", "b"], ["1"]]}]
    markdown = UnifiedOutputFormatter.to_markdown(_parse_result(blocks))
    assert "| 1 |  |" in markdown


def test_table_with_empty_header_is_skipped() -> None:
    blocks = [{"type": "table", "rows": [[]]}]
    assert UnifiedOutputFormatter.to_markdown(_parse_result(blocks)) == ""


def test_code_block_with_backticks_uses_longer_fence() -> None:
    blocks = [{"type": "code", "language": "text", "text": "a ``` b"}]
    markdown = UnifiedOutputFormatter.to_markdown(_parse_result(blocks))
    assert "````text" in markdown
    assert "a ``` b" in markdown


def test_formula_with_dollar_signs_escaped() -> None:
    blocks = [{"type": "formula", "text": "a $$ b"}]
    markdown = UnifiedOutputFormatter.to_markdown(_parse_result(blocks))
    assert "$$a \\$\\$ b$$" in markdown


def test_formula_latex_field_is_used() -> None:
    blocks = [{"type": "formula", "latex": "x^2"}]
    markdown = UnifiedOutputFormatter.to_markdown(_parse_result(blocks))
    assert "$$x^2$$" in markdown


def test_format_blocks_preserves_page_count() -> None:
    result = UnifiedOutputFormatter.format_blocks(
        [],
        "pdf",
        {"parser": "pdf"},
        page_count=12,
    )
    assert result.json_data["page_count"] == 12


@pytest.mark.asyncio
async def test_persist_writes_markdown_and_json() -> None:
    db = FakeDB()
    task_id = uuid.uuid4()
    file_id = uuid.uuid4()
    result = _parse_result([{"type": "paragraph", "text": "hi"}])

    await UnifiedOutputFormatter.persist_parse_results(db, task_id, file_id, result)

    assert len(db.added) == 2
    assert {row.output_format for row in db.added} == {"markdown", "json"}
    assert all(row.task_id == task_id for row in db.added)
    assert all(row.file_id == file_id for row in db.added)
    assert all(row.output_size and row.output_size > 0 for row in db.added)
    assert db.commits == 0
