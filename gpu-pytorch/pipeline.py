"""GPU container-side image pipeline."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Callable

from engines.formula import FormulaEngine
from engines.layout import (
    GPUModelNotReadyError as LayoutModelNotReadyError,
    GPUUnavailableError as LayoutUnavailableError,
    LayoutEngine,
)
from engines.ocr import OCREngine
from engines.reading_order import Region, sort_regions
from engines.table import TableEngine


class ImagePipeline:
    """Orchestrate layout, OCR, table, and formula engines on the GPU host."""

    def __init__(
        self,
        layout_engine: LayoutEngine | None = None,
        ocr_engine: OCREngine | None = None,
        table_engine: TableEngine | None = None,
        formula_engine: FormulaEngine | None = None,
        sort_regions_func: Callable[[list[Region]], list[Region]] | None = None,
    ) -> None:
        self.layout_engine = layout_engine or LayoutEngine()
        self.ocr_engine = ocr_engine or OCREngine()
        self.table_engine = table_engine or TableEngine()
        self.formula_engine = formula_engine or FormulaEngine()
        self.sort_regions = sort_regions_func or sort_regions

    def run(self, image_bytes: bytes) -> list[dict[str, Any]]:
        image_path = Path("/tmp") / f"image-pipeline-{uuid.uuid4().hex}.png"
        image_path.write_bytes(image_bytes)
        try:
            try:
                regions = self.layout_engine.detect(image_path)
            except (LayoutModelNotReadyError, LayoutUnavailableError):
                regions = []

            if not regions:
                items = self.ocr_engine.recognize(image_path)
                return [
                    {
                        "type": "paragraph",
                        "text": item["text"],
                        "bbox": item["bbox"],
                        "confidence": item["confidence"],
                        "page": 1,
                    }
                    for item in items
                ]

            blocks: list[dict[str, Any]] = []
            image_index = 0
            for region in self.sort_regions(regions):
                class_name = region["class"].lower()
                bbox = region["bbox"]
                if class_name == "title":
                    items = self.ocr_engine.recognize(image_path)
                    text = " ".join(item["text"] for item in items)
                    blocks.append(
                        {
                            "type": "heading",
                            "level": 2,
                            "text": text,
                            "bbox": bbox,
                            "page": 1,
                        }
                    )
                elif class_name == "text":
                    items = self.ocr_engine.recognize(image_path)
                    text = " ".join(item["text"] for item in items)
                    blocks.append(
                        {
                            "type": "paragraph",
                            "text": text,
                            "bbox": bbox,
                            "page": 1,
                        }
                    )
                elif class_name == "table":
                    table = self.table_engine.predict(image_path)
                    blocks.append(
                        {
                            "type": "table",
                            "rows": table["rows"],
                            "bbox": table["bbox"],
                            "page": 1,
                        }
                    )
                elif class_name == "formula":
                    formula = self.formula_engine.recognize(image_path)
                    blocks.append(
                        {
                            "type": "formula",
                            "latex": formula["latex"],
                            "page": 1,
                        }
                    )
                else:
                    image_index += 1
                    blocks.append(
                        {
                            "type": "image",
                            "src": f"image-{image_index}",
                            "bbox": bbox,
                            "caption": "",
                            "page": 1,
                        }
                    )
            return blocks
        finally:
            image_path.unlink(missing_ok=True)
