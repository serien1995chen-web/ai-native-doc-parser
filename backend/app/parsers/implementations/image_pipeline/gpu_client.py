"""HTTP client for GPU inference services."""

from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_TIMEOUT = 30.0
DEFAULT_PYTORCH_URL = "http://gpu-pytorch:8001"
DEFAULT_PADDLE_URL = "http://gpu-paddle:8002"

MOCK_RESULTS: dict[str, dict[str, Any]] = {
    "layout": {"detections": []},
    "ocr": {"items": []},
    "table": {"rows": [], "bbox": []},
    "formula": {"latex": ""},
}


class GPUInferenceClient:
    """Call GPU services with a unified fallback contract."""

    def __init__(
        self,
        timeout: float | None = None,
        pytorch_url: str | None = None,
        paddle_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.timeout = timeout if timeout is not None else DEFAULT_TIMEOUT
        self.pytorch_url = (pytorch_url or os.environ.get(
            "PYTORCH_INFER_URL", DEFAULT_PYTORCH_URL
        )).rstrip("/")
        self.paddle_url = (paddle_url or os.environ.get(
            "PADDLE_INFER_URL", DEFAULT_PADDLE_URL
        )).rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=self.timeout)

    async def _post(
        self,
        url: str,
        image_bytes: bytes,
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        """Post an image to a GPU endpoint with mock fallback on failure."""
        try:
            response = await self._client.post(
                url,
                files={"file": ("image.png", image_bytes, "image/png")},
            )
            response.raise_for_status()
            data = response.json()
            return {"gpu_unavailable": False, "data": data, "error": None}
        except Exception as exc:
            return {"gpu_unavailable": True, "data": fallback, "error": str(exc)}

    async def infer_layout(self, image_bytes: bytes) -> dict[str, Any]:
        """Run layout analysis on the PyTorch GPU service."""
        return await self._post(
            f"{self.pytorch_url}/layout",
            image_bytes,
            MOCK_RESULTS["layout"],
        )

    async def infer_ocr(self, image_bytes: bytes) -> dict[str, Any]:
        """Run OCR on the Paddle GPU service."""
        return await self._post(
            f"{self.paddle_url}/ocr",
            image_bytes,
            MOCK_RESULTS["ocr"],
        )

    async def infer_table(self, image_bytes: bytes) -> dict[str, Any]:
        """Run table detection on the PyTorch GPU service."""
        return await self._post(
            f"{self.pytorch_url}/table",
            image_bytes,
            MOCK_RESULTS["table"],
        )

    async def infer_formula(self, image_bytes: bytes) -> dict[str, Any]:
        """Run formula recognition on the PyTorch GPU service."""
        return await self._post(
            f"{self.pytorch_url}/formula",
            image_bytes,
            MOCK_RESULTS["formula"],
        )

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
