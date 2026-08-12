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

MODEL_BASE = Path(os.environ.get("MODEL_BASE", "/models"))

app = FastAPI(title="GPU PyTorch Inference", version="1.0.0")


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


def _layout_model_path() -> Path:
    candidates = sorted((MODEL_BASE / "doclayout_yolo").glob("*.pt"))
    if not candidates:
        raise HTTPException(
            status_code=503,
            detail="doclayout_yolo model not found under /models/doclayout_yolo",
        )
    return candidates[0]


def _run_layout(image_path: Path) -> dict[str, Any]:
    try:
        from doclayout_yolo import YOLOv10

        model = YOLOv10(str(_layout_model_path()))
        results = model.predict(str(image_path), imgsz=1024, conf=0.2, device="cuda:0")
        boxes = results[0].boxes
        class_names = results[0].names
        detections = []
        for row in boxes.data.cpu().numpy().tolist():
            x0, y0, x1, y1, confidence, class_id = row
            class_name = str(class_id)
            if isinstance(class_names, dict):
                class_name = str(class_names.get(int(class_id), class_name))
            else:
                try:
                    class_name = str(class_names[int(class_id)])
                except Exception:
                    class_name = str(class_id)
            detections.append(
                {
                    "class": class_name,
                    "bbox": [float(x0), float(y0), float(x1), float(y1)],
                    "confidence": float(confidence),
                }
            )
        return {"detections": detections}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _run_table(image_path: Path) -> dict[str, Any]:
    try:
        from PIL import Image
        from transformers import AutoImageProcessor, TableTransformerForObjectDetection

        model_dir = MODEL_BASE / "table-transformer-detection"
        model_name = (
            str(model_dir)
            if model_dir.exists()
            else "microsoft/table-transformer-detection"
        )
        processor = AutoImageProcessor.from_pretrained(model_name)
        model = TableTransformerForObjectDetection.from_pretrained(model_name)

        image_obj = Image.open(image_path).convert("RGB")
        inputs = processor(images=image_obj, return_tensors="pt")
        outputs = model(**inputs)
        target_sizes = [image_obj.size[::-1]]
        result = processor.post_process_object_detection(
            outputs, threshold=0.9, target_sizes=target_sizes
        )[0]
        boxes = result["boxes"].tolist()
        bbox = [float(value) for value in boxes[0]] if boxes else []
        return {"rows": [], "bbox": bbox}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _run_formula(image_path: Path) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={
            "detail": "UniMERNet integration is not ready",
            "code": "GPU_MODEL_NOT_READY",
        },
    )


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


@app.post("/infer")
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