"""HTTP-side image pipeline and parser."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from time import perf_counter
from typing import Any, Awaitable, Callable

from PIL import Image

from app.parsers.base import BaseParser, ParseResult, ParserInfo
from app.parsers.implementations.image_pipeline.gpu_client import GPUInferenceClient
from app.parsers.registry import ParserRegistry

SCHEMA_VERSION = "1.0"

def _run_async(
    awaitable_factory: Callable[[], Awaitable[list[dict[str, Any]]]],
) -> list[dict[str, Any]]:
    """Run an async pipeline call in a worker thread and block for the result."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, awaitable_factory()).result()


def _sort_regions(regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort regions top-to-bottom, left-to-right within a line."""
    if not regions:
        return []
    for region in regions:
        bbox = region.get("bbox")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            return list(regions)
        if not all(isinstance(value, (int, float)) for value in bbox):
            return list(regions)

    centers = []
    heights = []
    for region in regions:
        bbox = region["bbox"]
        centers.append(
            ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)
        )
        heights.append(max(bbox[3] - bbox[1], 0.0))
    tolerance = max(8.0, max(heights) * 0.35)
    ordered = sorted(range(len(regions)), key=lambda index: centers[index][1])

    lines: list[list[int]] = []
    for index in ordered:
        if not lines:
            lines.append([index])
            continue
        last_index = lines[-1][0]
        if abs(centers[index][1] - centers[last_index][1]) <= tolerance:
            lines[-1].append(index)
        else:
            lines.append([index])

    result: list[dict[str, Any]] = []
    for line in sorted(
        lines, key=lambda line: min(centers[index][1] for index in line)
    ):
        for index in sorted(line, key=lambda index: centers[index][0]):
            result.append(regions[index])
    return result


def _crop_image(image_bytes: bytes, bbox: list[float]) -> bytes:
    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    x0, y0, x1, y1 = [float(value) for value in bbox]
    left = max(0, int(x0))
    top = max(0, int(y0))
    right = min(image.width, int(x1))
    bottom = min(image.height, int(y1))
    if right <= left or bottom <= top:
        return image_bytes
    cropped = image.crop((left, top, right, bottom))
    buffer = BytesIO()
    cropped.save(buffer, format="PNG")
    return buffer.getvalue()


class ImagePipeline:
    """Call GPU services and assemble unified image blocks."""

    def __init__(self, client: GPUInferenceClient | None = None) -> None:
        self.client = client or GPUInferenceClient()

    async def run(
        self,
        image_bytes: bytes,
        image_type: str = "image",
    ) -> list[dict[str, Any]]:
        if image_type == "image_formula":
            result = await self.client.infer_formula(image_bytes)
            if result["gpu_unavailable"]:
                raise RuntimeError("GPU services unavailable")
            return [
                {
                    "type": "formula",
                    "latex": result["data"].get("latex", ""),
                    "page": 1,
                }
            ]

        if image_type == "image_table":
            result = await self.client.infer_table(image_bytes)
            if result["gpu_unavailable"]:
                raise RuntimeError("GPU services unavailable")
            data = result["data"]
            return [
                {
                    "type": "table",
                    "rows": data.get("rows", []),
                    "bbox": data.get("bbox", []),
                    "page": 1,
                }
            ]

        layout_result = await self.client.infer_layout(image_bytes)
        detections = (
            layout_result["data"].get("detections", [])
            if not layout_result["gpu_unavailable"]
            else []
        )
        if not detections:
            ocr_result = await self.client.infer_ocr(image_bytes)
            if ocr_result["gpu_unavailable"]:
                raise RuntimeError("GPU services unavailable")
            items = ocr_result["data"].get("items", [])
            return [
                {
                    "type": "paragraph",
                    "text": item.get("text", ""),
                    "bbox": item.get("bbox", []),
                    "confidence": item.get("confidence", 0.0),
                    "page": 1,
                }
                for item in items
            ]

        blocks: list[dict[str, Any]] = []
        image_index = 0
        for detection in _sort_regions(detections):
            class_name = str(detection.get("class", "")).lower()
            bbox = detection.get("bbox", [])
            crop_bytes = _crop_image(image_bytes, bbox) if bbox else image_bytes
            if class_name in ("text", "title"):
                ocr_result = await self.client.infer_ocr(crop_bytes)
                if ocr_result["gpu_unavailable"]:
                    raise RuntimeError("GPU services unavailable")
                text = " ".join(
                    item.get("text", "")
                    for item in ocr_result["data"].get("items", [])
                )
                if class_name == "title":
                    blocks.append(
                        {
                            "type": "heading",
                            "level": 2,
                            "text": text,
                            "bbox": bbox,
                            "page": 1,
                        }
                    )
                else:
                    blocks.append(
                        {
                            "type": "paragraph",
                            "text": text,
                            "bbox": bbox,
                            "page": 1,
                        }
                    )
            elif class_name == "table":
                table_result = await self.client.infer_table(crop_bytes)
                if table_result["gpu_unavailable"]:
                    raise RuntimeError("GPU services unavailable")
                data = table_result["data"]
                blocks.append(
                    {
                        "type": "table",
                        "rows": data.get("rows", []),
                        "bbox": data.get("bbox", bbox),
                        "page": 1,
                    }
                )
            elif class_name == "formula":
                formula_result = await self.client.infer_formula(crop_bytes)
                if formula_result["gpu_unavailable"]:
                    raise RuntimeError("GPU services unavailable")
                blocks.append(
                    {
                        "type": "formula",
                        "latex": formula_result["data"].get("latex", ""),
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


class ImagePipelineParser(BaseParser):
    """Parser that converts images into unified blocks through GPU services."""

    def __init__(self, pipeline: ImagePipeline | None = None) -> None:
        self._pipeline = pipeline or ImagePipeline()

    def info(self) -> ParserInfo:
        return ParserInfo(
            name="image_pipeline_parser",
            supported_types=[
                "image",
                "jpg",
                "png",
                "bmp",
                "image_formula",
                "image_table",
            ],
            required_gpu=True,
            required_models=[
                "doclayout_yolo",
                "paddleocr",
                "table_transformer",
                "unimernet",
            ],
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
        image_bytes = path.read_bytes()
        image_type = (options or {}).get("image_type", "image")
        blocks = _run_async(lambda: self._pipeline.run(image_bytes, image_type=image_type))
        processing_time_ms = round((perf_counter() - started) * 1000, 3)
        json_data = {
            "schema_version": SCHEMA_VERSION,
            "file_type": image_type,
            "page_count": 1,
            "blocks": blocks,
            "meta": {
                "parser": "image_pipeline_parser",
                "processing_time_ms": processing_time_ms,
            },
        }
        return ParseResult(
            markdown="",
            json_data=json_data,
            page_count=1,
            processing_time_ms=processing_time_ms,
        )


ParserRegistry.register(ImagePipelineParser())
