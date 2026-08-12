"""Unit tests for GPUInferenceClient."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.parsers.implementations.image_pipeline.gpu_client import GPUInferenceClient

pytestmark = pytest.mark.unit

CASES = [
    (
        "infer_layout",
        "http://pytorch.test/layout",
        {
            "detections": [
                {"class": "text", "bbox": [1, 2, 3, 4], "confidence": 0.9}
            ]
        },
        {"detections": []},
    ),
    (
        "infer_ocr",
        "http://paddle.test/ocr",
        {
            "items": [
                {"text": "hello", "bbox": [1, 2, 3, 4], "confidence": 0.9}
            ]
        },
        {"items": []},
    ),
    (
        "infer_table",
        "http://pytorch.test/table",
        {"rows": [["a", "b"]], "bbox": [1, 2, 3, 4]},
        {"rows": [], "bbox": []},
    ),
    (
        "infer_formula",
        "http://pytorch.test/formula",
        {"latex": "x^2"},
        {"latex": ""},
    ),
]


def _make_client(handler: Any) -> tuple[GPUInferenceClient, httpx.AsyncClient]:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    gpu_client = GPUInferenceClient(
        pytorch_url="http://pytorch.test",
        paddle_url="http://paddle.test",
        client=client,
    )
    return gpu_client, client


@pytest.mark.parametrize(("method", "url", "success_data", "fallback_data"), CASES)
async def test_infer_success(
    method: str,
    url: str,
    success_data: dict[str, Any],
    fallback_data: dict[str, Any],
) -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["content_type"] = request.headers.get("content-type", "")
        seen["has_file_field"] = b'name="file"' in request.content
        return httpx.Response(200, json=success_data)

    client, _ = _make_client(handler)
    result = await getattr(client, method)(b"image-bytes")
    assert result == {
        "gpu_unavailable": False,
        "data": success_data,
        "error": None,
    }
    assert seen["url"] == url
    assert "multipart/form-data" in seen["content_type"]
    assert seen["has_file_field"]
    await client.aclose()


@pytest.mark.parametrize(("method", "url", "success_data", "fallback_data"), CASES)
async def test_infer_http_failure(
    method: str,
    url: str,
    success_data: dict[str, Any],
    fallback_data: dict[str, Any],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "unavailable"})

    client, _ = _make_client(handler)
    result = await getattr(client, method)(b"image-bytes")
    assert result["gpu_unavailable"] is True
    assert result["data"] == fallback_data
    assert result["error"] is not None
    assert "503" in result["error"]
    await client.aclose()


@pytest.mark.parametrize(("method", "url", "success_data", "fallback_data"), CASES)
async def test_infer_timeout(
    method: str,
    url: str,
    success_data: dict[str, Any],
    fallback_data: dict[str, Any],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    client, _ = _make_client(handler)
    result = await getattr(client, method)(b"image-bytes")
    assert result["gpu_unavailable"] is True
    assert result["data"] == fallback_data
    assert "timed out" in result["error"]
    await client.aclose()


async def test_infer_invalid_json_returns_fallback() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    client, _ = _make_client(handler)
    result = await client.infer_layout(b"image-bytes")
    assert result["gpu_unavailable"] is True
    assert result["data"] == {"detections": []}
    assert result["error"] is not None
    await client.aclose()


async def test_aclose_closes_client() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    client, http_client = _make_client(handler)
    await client.aclose()
    assert http_client.is_closed
