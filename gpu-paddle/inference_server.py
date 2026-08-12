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


def _parse_ocr_entry(entry: Any) -> dict[str, Any] | None:
    if isinstance(entry, dict):
        text = str(entry.get("text") or "")
        bbox = entry.get("bbox") or []
        confidence = entry.get("confidence")
        if not isinstance(bbox, list):
            bbox = []
        return {
            "text": text,
            "bbox": [float(value) for value in bbox],
            "confidence": float(confidence) if confidence is not None else 0.0,
        }
    if isinstance(entry, (list, tuple)) and len(entry) >= 2:
        box, text_conf = entry[0], entry[1]
        if isinstance(text_conf, (list, tuple)) and len(text_conf) >= 2:
            text = str(text_conf[0] or "")
            confidence = text_conf[1] if text_conf[1] is not None else 0.0
            if isinstance(box, list):
                bbox = [float(value) for value in box]
            else:
                bbox = []
            return {
                "text": text,
                "bbox": bbox,
                "confidence": float(confidence),
            }
    return None


def _normalize_ocr_result(result: Any) -> dict[str, list[dict[str, Any]]]:
    items: list[dict[str, Any]] = []
    raw_items = result
    if isinstance(result, dict):
        raw_items = result.get("res") or result.get("result") or []
    if isinstance(raw_items, list):
        for image_result in raw_items:
            entries = image_result
            if isinstance(image_result, dict):
                entries = image_result.get("res") or image_result.get("result") or []
            if not isinstance(entries, list):
                continue
            for entry in entries:
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