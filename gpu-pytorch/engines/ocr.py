"""OCR engine for the PyTorch GPU container."""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict


class GPUModelNotReadyError(Exception):
    """Raised when PaddleOCR is missing or cannot initialize."""


class GPUUnavailableError(Exception):
    """Raised when OCR inference cannot run."""


OCRItem = TypedDict(
    "OCRItem",
    {"text": str, "bbox": list[float], "confidence": float},
)


def _bbox_to_rect(bbox: Any) -> list[float]:
    """Convert a flat bbox or nested polygon into a bounding rectangle."""
    if not isinstance(bbox, (list, tuple)):
        return []
    if len(bbox) == 4 and all(isinstance(value, (int, float)) for value in bbox):
        x0, y0, x1, y1 = (float(value) for value in bbox)
        return [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]
    points = []
    for point in bbox:
        if (
            isinstance(point, (list, tuple))
            and len(point) >= 2
            and all(isinstance(value, (int, float)) for value in point[:2])
        ):
            points.append((float(point[0]), float(point[1])))
    if not points:
        return []
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def _build_item(text: str, bbox: Any, confidence: Any) -> OCRItem:
    return {
        "text": text,
        "bbox": _bbox_to_rect(bbox) if bbox is not None else [],
        "confidence": float(confidence) if confidence is not None else 0.0,
    }


def _entry_from_dict(entry: dict[str, Any]) -> OCRItem | None:
    text = entry.get("text")
    if "bbox" in entry:
        bbox = entry["bbox"]
    elif "points" in entry:
        bbox = entry["points"]
    elif "rec_poly" in entry:
        bbox = entry["rec_poly"]
    else:
        bbox = None
    if "confidence" in entry:
        confidence = entry["confidence"]
    elif "score" in entry:
        confidence = entry["score"]
    elif "rec_score" in entry:
        confidence = entry["rec_score"]
    else:
        confidence = None
    if text is None:
        return None
    return _build_item(str(text), bbox, confidence)


def _parse_ocr_entry(entry: Any) -> OCRItem | None:
    if isinstance(entry, dict):
        return _entry_from_dict(entry)
    if isinstance(entry, (list, tuple)) and len(entry) >= 2:
        box, text_conf = entry[0], entry[1]
        if isinstance(text_conf, (list, tuple)) and len(text_conf) >= 2:
            text = str(text_conf[0] or "")
            confidence = text_conf[1] if text_conf[1] is not None else 0.0
            return _build_item(text, box, confidence)
    return None


def _normalize_ocr_result(result: Any) -> dict[str, list[OCRItem]]:
    items: list[OCRItem] = []
    if isinstance(result, dict):
        rec_texts = result.get("rec_texts")
        if isinstance(rec_texts, list):
            rec_scores = result.get("rec_scores")
            rec_polys = result.get("rec_polys")
            for index, text in enumerate(rec_texts):
                bbox = (
                    rec_polys[index]
                    if isinstance(rec_polys, list) and index < len(rec_polys)
                    else None
                )
                confidence = (
                    rec_scores[index]
                    if isinstance(rec_scores, list) and index < len(rec_scores)
                    else None
                )
                items.append(_build_item(str(text or ""), bbox, confidence))
            return {"items": items}
        texts = result.get("text")
        bboxes = result.get("bbox") or result.get("points")
        scores = result.get("confidence") or result.get("score")
        if isinstance(texts, list) and isinstance(bboxes, list):
            for index, text in enumerate(texts):
                bbox = bboxes[index] if index < len(bboxes) else None
                confidence = (
                    scores[index]
                    if isinstance(scores, list) and index < len(scores)
                    else None
                )
                items.append(_build_item(str(text or ""), bbox, confidence))
            return {"items": items}
        nested = result.get("res") or result.get("result")
        if nested is not None:
            return _normalize_ocr_result(nested)
        parsed = _entry_from_dict(result)
        if parsed:
            items.append(parsed)
    elif isinstance(result, list):
        for image_result in result:
            if isinstance(image_result, dict):
                nested = _normalize_ocr_result(image_result)
                items.extend(nested["items"])
            elif isinstance(image_result, list):
                for entry in image_result:
                    parsed = _parse_ocr_entry(entry)
                    if parsed:
                        items.append(parsed)
    return {"items": items}


class OCREngine:
    """Run PaddleOCR with lazy model initialization."""

    def __init__(self) -> None:
        self._ocr: Any | None = None

    def _get_ocr(self) -> Any:
        if self._ocr is None:
            try:
                from paddleocr import PaddleOCR
            except Exception as exc:
                raise GPUModelNotReadyError(
                    f"Failed to import PaddleOCR: {exc}"
                ) from exc
            try:
                self._ocr = PaddleOCR(
                    use_angle_cls=True, lang="ch", show_log=False
                )
            except Exception as exc:
                raise GPUModelNotReadyError(
                    f"Failed to initialize PaddleOCR: {exc}"
                ) from exc
        return self._ocr

    def recognize(self, image_path: str | Path) -> list[OCRItem]:
        path = Path(image_path)
        if not path.is_file():
            raise GPUUnavailableError(f"Image file not found: {image_path}")
        ocr = self._get_ocr()
        try:
            result = ocr.ocr(str(path), cls=True)
        except Exception as exc:
            raise GPUUnavailableError(f"OCR inference failed: {exc}") from exc
        return _normalize_ocr_result(result)["items"]
