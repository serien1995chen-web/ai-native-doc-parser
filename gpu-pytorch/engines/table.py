"""Table detection engine for the PyTorch GPU service."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, TypedDict


class GPUModelNotReadyError(Exception):
    """Raised when the table model is missing or cannot initialize."""


class GPUUnavailableError(Exception):
    """Raised when table inference cannot run."""


TableResult = TypedDict(
    "TableResult",
    {"rows": list[list[str]], "bbox": list[float]},
)


class TableEngine:
    """Run TableTransformer detection with lazy model loading."""

    def __init__(self, model_base: str | Path | None = None) -> None:
        self.model_base = Path(
            model_base or os.environ.get("MODEL_BASE", "/models")
        )
        self._model: Any | None = None
        self._processor: Any | None = None

    def _model_name(self) -> str:
        model_dir = self.model_base / "table-transformer-detection"
        if model_dir.exists():
            return str(model_dir)
        return "microsoft/table-transformer-detection"

    def _get_components(self) -> tuple[Any, Any]:
        if self._model is None or self._processor is None:
            try:
                from transformers import (
                    AutoImageProcessor,
                    TableTransformerForObjectDetection,
                )
            except Exception as exc:
                raise GPUUnavailableError(
                    f"Failed to import table transformer: {exc}"
                ) from exc
            try:
                model_name = self._model_name()
                self._processor = AutoImageProcessor.from_pretrained(model_name)
                self._model = TableTransformerForObjectDetection.from_pretrained(
                    model_name
                )
            except Exception as exc:
                raise GPUModelNotReadyError(
                    f"Failed to load table transformer model: {exc}"
                ) from exc
        return self._processor, self._model

    def predict(self, image_path: str | Path) -> TableResult:
        path = Path(image_path)
        if not path.is_file():
            raise GPUUnavailableError(f"Image file not found: {image_path}")
        processor, model = self._get_components()
        try:
            from PIL import Image

            image_obj = Image.open(path).convert("RGB")
            inputs = processor(images=image_obj, return_tensors="pt")
            outputs = model(**inputs)
            target_sizes = [image_obj.size[::-1]]
            result = processor.post_process_object_detection(
                outputs, threshold=0.9, target_sizes=target_sizes
            )[0]
        except Exception as exc:
            raise GPUUnavailableError(f"Table inference failed: {exc}") from exc
        boxes = result["boxes"].tolist()
        bbox = [float(value) for value in boxes[0]] if boxes else []
        return {"rows": [], "bbox": bbox}
