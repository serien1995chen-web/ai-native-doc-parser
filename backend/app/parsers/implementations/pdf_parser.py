"""PDF document parser using PyMuPDF."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

import fitz

from app.parsers.base import BaseParser, ParseResult, ParserInfo
from app.parsers.registry import ParserRegistry

SCHEMA_VERSION = "1.0"


class PDFParser(BaseParser):
    """Parse PDF files into unified document blocks."""

    def info(self) -> ParserInfo:
        return ParserInfo(
            name="pdf_parser",
            supported_types=["pdf"],
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

        blocks: list[dict[str, Any]] = []
        image_index = 0
        with fitz.open(path) as document:
            for page_number, page in enumerate(document, start=1):
                blocks.append(
                    {
                        "type": "heading",
                        "level": 2,
                        "text": f"Page {page_number}",
                        "page": page_number,
                    }
                )
                for text_block in page.get_text("blocks"):
                    text = text_block[4].strip()
                    if not text:
                        continue
                    blocks.append(
                        {
                            "type": "paragraph",
                            "text": text,
                            "bbox": [
                                float(text_block[0]),
                                float(text_block[1]),
                                float(text_block[2]),
                                float(text_block[3]),
                            ],
                            "page": page_number,
                        }
                    )
                for image_info in page.get_images(full=True):
                    rects = page.get_image_rects(image_info[0])
                    bbox = [float(value) for value in rects[0]] if rects else []
                    image_index += 1
                    blocks.append(
                        {
                            "type": "image",
                            "src": f"image-{image_index}",
                            "bbox": bbox,
                            "caption": "",
                            "page": page_number,
                        }
                    )
            page_count = document.page_count

        processing_time_ms = round((perf_counter() - started) * 1000, 3)
        json_data = {
            "schema_version": SCHEMA_VERSION,
            "file_type": "pdf",
            "page_count": page_count,
            "blocks": blocks,
            "meta": {
                "parser": "pdf_parser",
                "processing_time_ms": processing_time_ms,
            },
        }
        return ParseResult(
            markdown="",
            json_data=json_data,
            page_count=page_count,
            processing_time_ms=processing_time_ms,
        )


ParserRegistry.register(PDFParser())
