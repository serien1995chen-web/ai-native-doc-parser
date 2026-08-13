"""Layout analysis engine for the PyTorch GPU service."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, TypedDict


class GPUModelNotReadyError(Exception):
    """Raised when the layout model is missing or cannot initialize."""


class GPUUnavailableError(Exception):
    """Raised when layout inference cannot run."""


LayoutRegion = TypedDict(
    "LayoutRegion",
    {"class": str, "bbox": list[float], "confidence": float},
)

ALLOWED_CLASSES = {"text", "title", "table", "formula", "figure"}


class LayoutEngine:
    """Run DocLayout-YOLO layout detection with lazy model loading."""

    def __init__(self, model_base: str | Path | None = None) -> None:
        self.model_base = Path(
            model_base or os.environ.get("MODEL_BASE", "/models")
        )
        self._model: Any | None = None

    def _find_model(self) -> Path:
        candidates = sorted((self.model_base / "doclayout_yolo").glob("*.pt"))
        if not candidates:
            raise GPUModelNotReadyError(
                "doclayout_yolo model not found under "
                f"{self.model_base / 'doclayout_yolo'}"
            )
        return candidates[0]

    def _get_model(self) -> Any:
        if self._model is None:
            model_path = self._find_model()
            try:
                from doclayout_yolo import YOLOv10
            except Exception as exc:
                raise GPUUnavailableError(
                    f"Failed to import doclayout_yolo: {exc}"
                ) from exc
            try:
                self._model = YOLOv10(str(model_path))
            except Exception as exc:
                raise GPUUnavailableError(
                    f"Failed to load doclayout_yolo model: {exc}"
                ) from exc
        return self._model

    @staticmethod
    def _class_name(class_id: float, names: Any) -> str:
        name = str(int(class_id))
        if isinstance(names, dict):
            name = str(names.get(int(class_id), name))
        elif isinstance(names, list):
            try:
                name = str(names[int(class_id)])
            except (IndexError, TypeError, ValueError):
                pass
        return name.lower()

    @classmethod
    def _normalize_rows(
        cls,
        rows: list[list[float]],
        names: Any,
    ) -> list[LayoutRegion]:
        normalized: list[LayoutRegion] = []
        for row in rows:
            x0, y0, x1, y1, confidence, class_id = row
            class_name = cls._class_name(class_id, names)
            if class_name not in ALLOWED_CLASSES:
                class_name = "text"
            normalized.append(
                {
                    "class": class_name,
                    "bbox": [float(x0), float(y0), float(x1), float(y1)],
                    "confidence": float(confidence),
                }
            )
        return normalized

    def detect(self, image_path: str | Path) -> list[LayoutRegion]:
        path = Path(image_path)
        if not path.is_file():
            raise GPUUnavailableError(f"Image file not found: {image_path}")
        model = self._get_model()
        try:
            results = model.predict(
                str(path), imgsz=1024, conf=0.2, device="cuda:0"
            )
        except Exception as exc:
            raise GPUUnavailableError(f"Layout inference failed: {exc}") from exc
        rows = results[0].boxes.data.cpu().numpy().tolist()
        return self._normalize_rows(rows, results[0].names)
