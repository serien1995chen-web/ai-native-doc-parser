"""HTML parser using BeautifulSoup."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

from bs4 import BeautifulSoup, Tag

from app.parsers.base import BaseParser, ParseResult, ParserInfo
from app.parsers.registry import ParserRegistry

SCHEMA_VERSION = "1.0"

HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")
BLOCK_TAGS = (*HEADING_TAGS, "p", "li", "table", "img")


def _has_block_descendant(tag: Tag) -> bool:
    """Return True when a container has a block-level descendant."""
    return tag.find(BLOCK_TAGS) is not None


def _walk_container(
    tag: Tag,
    blocks: list[dict[str, Any]],
    image_index: int,
) -> tuple[list[dict[str, Any]], int]:
    """Walk HTML children in document order without duplicating nested divs."""
    for child in tag.children:
        if not isinstance(child, Tag):
            continue
        name = child.name.lower()
        if name in HEADING_TAGS:
            blocks.append(
                {
                    "type": "heading",
                    "level": int(name[1]),
                    "text": child.get_text(" ", strip=True),
                    "page": 1,
                }
            )
        elif name in ("p", "li"):
            text = child.get_text(" ", strip=True)
            if text:
                blocks.append({"type": "paragraph", "text": text, "page": 1})
        elif name == "table":
            rows = [
                [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
                for row in child.find_all("tr")
            ]
            blocks.append({"type": "table", "rows": rows, "page": 1})
        elif name == "img":
            image_index += 1
            blocks.append(
                {
                    "type": "image",
                    "src": f"image-{image_index}",
                    "bbox": [],
                    "caption": "",
                    "page": 1,
                }
            )
        elif name == "div":
            if _has_block_descendant(child):
                blocks, image_index = _walk_container(child, blocks, image_index)
            else:
                text = child.get_text(" ", strip=True)
                if text:
                    blocks.append({"type": "paragraph", "text": text, "page": 1})
        elif _has_block_descendant(child):
            blocks, image_index = _walk_container(child, blocks, image_index)
    return blocks, image_index


class HtmlParser(BaseParser):
    """Parse HTML files into unified document blocks."""

    def info(self) -> ParserInfo:
        return ParserInfo(
            name="html_parser",
            supported_types=["html", "htm"],
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
        soup = BeautifulSoup(content, "html.parser")
        blocks: list[dict[str, Any]] = []
        image_index = 0
        root = soup.body if soup.body is not None else soup
        blocks, image_index = _walk_container(root, blocks, image_index)

        processing_time_ms = round((perf_counter() - started) * 1000, 3)
        json_data = {
            "schema_version": SCHEMA_VERSION,
            "file_type": "html",
            "page_count": 1,
            "blocks": blocks,
            "meta": {
                "parser": "html_parser",
                "processing_time_ms": processing_time_ms,
            },
        }
        return ParseResult(
            markdown="",
            json_data=json_data,
            page_count=1,
            processing_time_ms=processing_time_ms,
        )


ParserRegistry.register(HtmlParser())
