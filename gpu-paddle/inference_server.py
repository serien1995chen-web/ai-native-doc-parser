"""FastAPI service for the PaddleOCR GPU inference container."""

from __future__ import annotations

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


def _save_upload(upload: UploadFile, name: str) -> Path:
    target = Path("/tmp") / name
    with target.open("wb") as handle:
        handle.write(upload.file.read())
    return target


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    cuda_available = False
    try:
        import paddle

        cuda_available = bool(paddle.device.is_compiled_with_cuda())
    except Exception:
        cuda_available = False
    return HealthResponse(status="ok", cuda_available=cuda_available)


@app.post("/ocr")
async def ocr(file: UploadFile = File(...)) -> dict[str, Any]:
    image = _save_upload(file, "ocr.png")
    try:
        from paddleocr import PaddleOCR

        ocr_engine = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
        result = ocr_engine.ocr(str(image), cls=True)
        return {"result": result}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8002
    )