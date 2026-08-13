"""Unified Markdown/JSON output formatting and persistence."""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.models import ParseResult as ORMResult
from app.parsers.base import ParseResult as ParserParseResult


class UnifiedOutputFormatter:
    """Convert parser blocks into Markdown/JSON and persist results."""

    @staticmethod
    def _blocks_to_markdown(blocks: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for block in blocks:
            block_type = block.get("type", "paragraph")
            if block_type == "heading":
                level = int(block.get("level", 1))
                text = str(block.get("text", ""))
                parts.append(f"{'#' * level} {text}")
            elif block_type == "paragraph":
                parts.append(str(block.get("text", "")))
            elif block_type == "table":
                rows = block.get("rows", [])
                if rows:
                    header = rows[0]
                    separator = ["---"] * len(header)
                    table_rows = [header, separator, *rows[1:]]
                    parts.append(
                        "\n".join(
                            "| " + " | ".join(str(cell) for cell in row) + " |"
                            for row in table_rows
                        )
                    )
            elif block_type == "image":
                src = str(block.get("src", ""))
                caption = str(block.get("caption", ""))
                parts.append(f"![{caption}]({src})")
            elif block_type == "formula":
                parts.append(f"$${block.get('text', '')}$$")
            elif block_type == "code":
                language = str(block.get("language", ""))
                text = str(block.get("text", ""))
                parts.append(f"```{language}\n{text}\n```")
            else:
                parts.append(str(block.get("text", "")))
        return "\n\n".join(parts).strip()

    @staticmethod
    def to_markdown(parse_result: ParserParseResult) -> str:
        blocks = parse_result.json_data.get("blocks", [])
        return UnifiedOutputFormatter._blocks_to_markdown(blocks)

    @staticmethod
    def to_json(parse_result: ParserParseResult) -> dict[str, Any]:
        return parse_result.json_data

    @staticmethod
    def format_blocks(
        blocks: list[dict[str, Any]],
        file_type: str,
        meta: dict[str, Any] | None = None,
    ) -> ParserParseResult:
        json_data: dict[str, Any] = {
            "schema_version": "1.0",
            "file_type": file_type,
            "page_count": None,
            "blocks": blocks,
            "meta": meta or {},
        }
        return ParserParseResult(
            markdown=UnifiedOutputFormatter._blocks_to_markdown(blocks),
            json_data=json_data,
        )

    @staticmethod
    async def persist_parse_results(
        db: Any,
        task_id: uuid.UUID,
        file_id: uuid.UUID,
        parse_result: ParserParseResult,
    ) -> None:
        markdown = UnifiedOutputFormatter.to_markdown(parse_result)
        json_text = json.dumps(parse_result.json_data, ensure_ascii=False)
        processing_time_ms = parse_result.processing_time_ms
        db.add(
            ORMResult(
                id=uuid.uuid4(),
                task_id=task_id,
                file_id=file_id,
                output_format="markdown",
                output_text=markdown,
                output_size=len(markdown.encode("utf-8")),
                processing_time_ms=processing_time_ms,
            )
        )
        db.add(
            ORMResult(
                id=uuid.uuid4(),
                task_id=task_id,
                file_id=file_id,
                output_format="json",
                output_text=json_text,
                output_size=len(json_text.encode("utf-8")),
                processing_time_ms=processing_time_ms,
            )
        )
        await db.commit()
