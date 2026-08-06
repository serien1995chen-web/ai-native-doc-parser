"""FastAPI service for the PyTorch GPU inference container."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

MODEL_BASE = Path(os.environ.get("MODEL_BASE", "/models"))

app = FastAPI(title="GPU PyTorch Inference", version="1.0.0")


class HealthResponse(BaseModel):
    status: str
    cuda_available: bool


def _save_upload(upload: UploadFile, name: str) -> Path:
    target = Path("/tmp") / name
    with target.open("wb") as handle:
        handle.write(upload.file.read())
    return target


def _layout_model_path() -> Path:
    candidates = sorted((MODEL_BASE / "doclayout_yolo").glob("*.pt"))
    if not candidates:
        raise HTTPException(
            status_code=503,
            detail="doclayout_yolo model not found under /models/doclayout_yolo",
        )
    return candidates[0]


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    cuda_available = False
    try:
        import torch

        cuda_available = bool(torch.cuda.is_available())
    except Exception:
        cuda_available = False
    return HealthResponse(status="ok", cuda_available=cuda_available)


@app.post("/layout")
async def layout(file: UploadFile = File(...)) -> dict[str, Any]:
    image = _save_upload(file, "layout.png")
    try:
        from doclayout_yolo import YOLOv10

        model = YOLOv10(str(_layout_model_path()))
        results = model.predict(str(image), imgsz=1024, conf=0.2, device="cuda:0")
        detections = results[0].boxes.data.cpu().numpy().tolist()
        return {"count": len(detections), "detections": detections}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/table")
async def table(file: UploadFile = File(...)) -> dict[str, Any]:
    image = _save_upload(file, "table.png")
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

        image_obj = Image.open(image).convert("RGB")
        inputs = processor(images=image_obj, return_tensors="pt")
        outputs = model(**inputs)
        target_sizes = [image_obj.size[::-1]]
        result = processor.post_process_object_detection(
            outputs, threshold=0.9, target_sizes=target_sizes
        )[0]
        return {
            "boxes": result["boxes"].tolist(),
            "labels": result["labels"].tolist(),
            "scores": result["scores"].tolist(),
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/formula")
async def formula(file: UploadFile = File(...)) -> dict[str, Any]:
    raise HTTPException(
        status_code=501,
        detail=(
            "UniMERNet integration requires a config and tokenizer under "
            "/models/unimernet; see gpu-pytorch/README.md"
        ),
    )
