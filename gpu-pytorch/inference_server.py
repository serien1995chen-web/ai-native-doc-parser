"""FastAPI service for the PyTorch GPU inference container."""

from __future__ import annotations

import base64
import binascii
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from engines.layout import (
    GPUModelNotReadyError,
    GPUUnavailableError,
    LayoutEngine,
)
from engines.formula import (
    FormulaEngine,
    GPUModelNotReadyError as FormulaModelNotReadyError,
    GPUUnavailableError as FormulaUnavailableError,
)
from engines.table import (
    TableEngine,
    GPUModelNotReadyError as TableModelNotReadyError,
    GPUUnavailableError as TableUnavailableError,
)

MODEL_BASE = Path(os.environ.get("MODEL_BASE", "/models"))

app = FastAPI(title="GPU PyTorch Inference", version="1.0.0")

_layout_engine = LayoutEngine()
_table_engine = TableEngine()
_formula_engine = FormulaEngine()


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


def _run_layout(image_path: Path) -> dict[str, Any]:
    try:
        detections = _layout_engine.detect(image_path)
        return {"detections": detections}
    except (GPUModelNotReadyError, GPUUnavailableError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _run_table(image_path: Path) -> dict[str, Any]:
    try:
        table = _table_engine.predict(image_path)
        return {"rows": table["rows"], "bbox": table["bbox"]}
    except (TableModelNotReadyError, TableUnavailableError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _run_formula(image_path: Path) -> dict[str, Any] | JSONResponse:
    try:
        return _formula_engine.recognize(image_path)
    except FormulaModelNotReadyError as exc:
        return JSONResponse(
            status_code=501,
            content={
                "detail": str(exc),
                "code": "GPU_MODEL_NOT_READY",
            },
        )
    except FormulaUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    cuda_available = False
    try:
        import torch

        cuda_available = bool(torch.cuda.is_available())
    except Exception:
        cuda_available = False
    return HealthResponse(status="ok", cuda_available=cuda_available)


@app.get("/models")
def models() -> dict[str, list[str]]:
    return {"models": ["layout", "table", "formula"]}


@app.post("/layout")
async def layout(file: UploadFile = File(...)) -> dict[str, Any]:
    image = _save_upload(file, "layout.png")
    return _run_layout(image)


@app.post("/table")
async def table(file: UploadFile = File(...)) -> dict[str, Any]:
    image = _save_upload(file, "table.png")
    return _run_table(image)


@app.post("/formula")
async def formula(file: UploadFile = File(...)) -> JSONResponse:
    image = _save_upload(file, "formula.png")
    return _run_formula(image)


@app.post("/infer", response_model=None)
async def infer(request: InferRequest) -> dict[str, Any] | JSONResponse:
    try:
        image_bytes = base64.b64decode(request.image_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="Invalid base64 image")
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Invalid base64 image")
    image_path = _save_bytes(image_bytes, "infer.png")
    if request.model_type == "layout":
        return _run_layout(image_path)
    if request.model_type == "table":
        return _run_table(image_path)
    if request.model_type == "formula":
        return _run_formula(image_path)
    raise HTTPException(
        status_code=400,
        detail=f"Unsupported model_type: {request.model_type}",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,
    )