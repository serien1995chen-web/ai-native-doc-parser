"""FastAPI service for the PaddleOCR GPU inference container."""

from __future__ import annotations

import base64
import binascii
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from engines.ocr import (
    GPUModelNotReadyError,
    GPUUnavailableError,
    OCREngine,
)

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


def _run_ocr(image_path: Path) -> dict[str, Any]:
    try:
        engine = OCREngine()
        items = engine.recognize(image_path)
        return {"items": items}
    except (GPUModelNotReadyError, GPUUnavailableError) as exc:
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