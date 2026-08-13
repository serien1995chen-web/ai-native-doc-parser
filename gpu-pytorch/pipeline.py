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

def _crop_image_path(image_path: Path, bbox: list[float], suffix: str) -> Path:
    from PIL import Image

    image = Image.open(image_path).convert("RGB")
    x0, y0, x1, y1 = [float(value) for value in bbox]
    left = max(0, int(x0))
    top = max(0, int(y0))
    right = min(image.width, int(x1))
    bottom = min(image.height, int(y1))
    crop_path = Path("/tmp") / f"image-crop-{uuid.uuid4().hex}-{suffix}.png"
    if right <= left or bottom <= top:
        image.close()
        crop_path.write_bytes(image_path.read_bytes())
    else:
        cropped = image.crop((left, top, right, bottom))
        cropped.save(crop_path, format="PNG")
        cropped.close()
        image.close()
    return crop_path


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
                    crop_path = _crop_image_path(image_path, bbox, "title")
                    try:
                        items = self.ocr_engine.recognize(crop_path)
                    finally:
                        crop_path.unlink(missing_ok=True)
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
                    crop_path = _crop_image_path(image_path, bbox, "text")
                    try:
                        items = self.ocr_engine.recognize(crop_path)
                    finally:
                        crop_path.unlink(missing_ok=True)
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
                    crop_path = _crop_image_path(image_path, bbox, "table")
                    try:
                        table = self.table_engine.predict(crop_path)
                    finally:
                        crop_path.unlink(missing_ok=True)
                    blocks.append(
                        {
                            "type": "table",
                            "rows": table["rows"],
                            "bbox": table["bbox"],
                            "page": 1,
                        }
                    )
                elif class_name == "formula":
                    crop_path = _crop_image_path(image_path, bbox, "formula")
                    try:
                        formula = self.formula_engine.recognize(crop_path)
                    finally:
                        crop_path.unlink(missing_ok=True)
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
