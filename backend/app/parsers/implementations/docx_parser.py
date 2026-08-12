"""DOCX document parser using python-docx."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any, Iterator

from docx import Document as DocxDocument
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.parsers.base import BaseParser, ParseResult, ParserInfo
from app.parsers.registry import ParserRegistry

SCHEMA_VERSION = "1.0"

HEADING_LEVELS = {f"Heading {level}": level for level in range(1, 7)}


def _iter_body_items(
    document: DocxDocument,
) -> Iterator[tuple[str, Paragraph | Table]]:
    """Yield paragraphs and tables in their original body order."""
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield "paragraph", Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield "table", Table(child, document)


def _heading_level(paragraph: Paragraph) -> int | None:
    """Map a paragraph style to a heading level, or return None."""
    style_name = paragraph.style.name if paragraph.style is not None else ""
    if style_name == "Title":
        return 1
    return HEADING_LEVELS.get(style_name)


class DocxParser(BaseParser):
    """Parse DOCX files into unified document blocks."""

    def info(self) -> ParserInfo:
        return ParserInfo(
            name="docx_parser",
            supported_types=["doc", "docx"],
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

        document = DocxDocument(str(path))
        blocks: list[dict[str, Any]] = []
        image_index = 0

        for item_type, item in _iter_body_items(document):
            if item_type == "paragraph":
                text = item.text.strip()
                level = _heading_level(item)
                if level is not None and text:
                    blocks.append(
                        {
                            "type": "heading",
                            "level": level,
                            "text": text,
                            "page": 1,
                        }
                    )
                elif text:
                    blocks.append({"type": "paragraph", "text": text, "page": 1})

                for blip in item._p.iter(qn("a:blip")):
                    if blip.get(qn("r:embed")):
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
            else:
                rows = [[cell.text.strip() for cell in row.cells] for row in item.rows]
                blocks.append({"type": "table", "rows": rows, "page": 1})

        processing_time_ms = round((perf_counter() - started) * 1000, 3)
        json_data = {
            "schema_version": SCHEMA_VERSION,
            "file_type": "docx",
            "page_count": 1,
            "blocks": blocks,
            "meta": {
                "parser": "docx_parser",
                "processing_time_ms": processing_time_ms,
            },
        }
        return ParseResult(
            markdown="",
            json_data=json_data,
            page_count=1,
            processing_time_ms=processing_time_ms,
        )


ParserRegistry.register(DocxParser())
