"""FastAPI service for the PaddleOCR GPU inference container."""

from __future__ import annotations

import base64
import binascii
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

MODEL_BASE = Path(os.environ.get("MODEL_BASE", "/models"))

app = FastAPI(title="GPU PaddleOCR Inference", version="1.0.0")


class HealthResponse(BaseModel):
    status: str
    cuda_available: bool


class InferRequest(BaseModel):
    model_type: str
    image_base64: str


def _save_bytes(image_bytes: bytes, name: str) -> Path:
    target = Path("/tmp") / name
    with target.open("wb") as handle:
        handle.write(image_bytes)
    return target


def _save_upload(upload: UploadFile, name: str) -> Path:
    return _save_bytes(upload.file.read(), name)


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


def _build_item(text: str, bbox: Any, confidence: Any) -> dict[str, Any]:
    return {
        "text": text,
        "bbox": _bbox_to_rect(bbox) if bbox is not None else [],
        "confidence": float(confidence) if confidence is not None else 0.0,
    }


def _entry_from_dict(entry: dict[str, Any]) -> dict[str, Any] | None:
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


def _parse_ocr_entry(entry: Any) -> dict[str, Any] | None:
    if isinstance(entry, dict):
        return _entry_from_dict(entry)
    if isinstance(entry, (list, tuple)) and len(entry) >= 2:
        box, text_conf = entry[0], entry[1]
        if isinstance(text_conf, (list, tuple)) and len(text_conf) >= 2:
            text = str(text_conf[0] or "")
            confidence = text_conf[1] if text_conf[1] is not None else 0.0
            return _build_item(text, box, confidence)
    return None


def _normalize_ocr_result(result: Any) -> dict[str, list[dict[str, Any]]]:
    items: list[dict[str, Any]] = []
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


def _run_ocr(image_path: Path) -> dict[str, Any]:
    try:
        from paddleocr import PaddleOCR

        ocr_engine = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
        result = ocr_engine.ocr(str(image_path), cls=True)
        return _normalize_ocr_result(result)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    cuda_available = False
    try:
        import paddle

        cuda_available = bool(paddle.device.is_compiled_with_cuda())
    except Exception:
        cuda_available = False
    return HealthResponse(status="ok", cuda_available=cuda_available)


@app.get("/models")
def models() -> dict[str, list[str]]:
    return {"models": ["ocr"]}


@app.post("/ocr")
async def ocr(file: UploadFile = File(...)) -> dict[str, Any]:
    image = _save_upload(file, "ocr.png")
    return _run_ocr(image)


@app.post("/infer")
async def infer(request: InferRequest) -> dict[str, Any]:
    if request.model_type != "ocr":
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported model_type: {request.model_type}",
        )
    try:
        image_bytes = base64.b64decode(request.image_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="Invalid base64 image")
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Invalid base64 image")
    image_path = _save_bytes(image_bytes, "infer.png")
    return _run_ocr(image_path)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8002,
    )