"""Unit tests for HTTP image pipeline and parser."""

from __future__ import annotations

import base64
import importlib
import importlib.util
import sys
from io import BytesIO
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.parsers.implementations.image_pipeline.pipeline import (
    ImagePipeline,
    ImagePipelineParser,
)
from app.parsers.registry import ParserRegistry

REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.unit


def _make_png() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (200, 200), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def _fake_client(
    layout: dict | None = None,
    ocr: dict | None = None,
    table: dict | None = None,
    formula: dict | None = None,
) -> AsyncMock:
    client = AsyncMock()
    client.infer_layout.return_value = layout or {
        "gpu_unavailable": True,
        "data": {},
        "error": "unavailable",
    }
    client.infer_ocr.return_value = ocr or {
        "gpu_unavailable": True,
        "data": {},
        "error": "unavailable",
    }
    client.infer_table.return_value = table or {
        "gpu_unavailable": True,
        "data": {},
        "error": "unavailable",
    }
    client.infer_formula.return_value = formula or {
        "gpu_unavailable": True,
        "data": {},
        "error": "unavailable",
    }
    return client


def _load_server_module(path: Path, module_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    for key in [
        module_key
        for module_key in list(sys.modules)
        if module_key == "engines" or module_key.startswith("engines.")
    ]:
        sys.modules.pop(key, None)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(path.parent))
    return module


@pytest.mark.asyncio
async def test_image_pipeline_layout_success() -> None:
    client = _fake_client(
        layout={
            "gpu_unavailable": False,
            "data": {
                "detections": [
                    {"class": "text", "bbox": [0, 0, 100, 50], "confidence": 0.9},
                    {"class": "table", "bbox": [0, 60, 100, 120], "confidence": 0.8},
                    {"class": "formula", "bbox": [0, 130, 100, 160], "confidence": 0.7},
                ]
            },
            "error": None,
        },
        ocr={
            "gpu_unavailable": False,
            "data": {
                "items": [
                    {"text": "hello", "bbox": [0, 0, 10, 10], "confidence": 0.9}
                ]
            },
            "error": None,
        },
        table={
            "gpu_unavailable": False,
            "data": {"rows": [["a"]], "bbox": [0, 60, 100, 120]},
            "error": None,
        },
        formula={
            "gpu_unavailable": False,
            "data": {"latex": "x^2"},
            "error": None,
        },
    )
    pipeline = ImagePipeline(client=client)
    blocks = await pipeline.run(_make_png())
    assert [block["type"] for block in blocks] == [
        "paragraph",
        "table",
        "formula",
    ]


@pytest.mark.asyncio
async def test_image_pipeline_layout_unavailable_falls_back_to_ocr() -> None:
    client = _fake_client(
        ocr={
            "gpu_unavailable": False,
            "data": {
                "items": [
                    {"text": "ocr line", "bbox": [1, 2, 3, 4], "confidence": 0.9}
                ]
            },
            "error": None,
        }
    )
    pipeline = ImagePipeline(client=client)
    blocks = await pipeline.run(_make_png())
    assert blocks == [
        {
            "type": "paragraph",
            "text": "ocr line",
            "bbox": [1, 2, 3, 4],
            "confidence": 0.9,
            "page": 1,
        }
    ]


@pytest.mark.asyncio
async def test_image_pipeline_formula_and_table_types() -> None:
    formula_client = _fake_client(
        formula={
            "gpu_unavailable": False,
            "data": {"latex": "E=mc^2"},
            "error": None,
        }
    )
    formula_blocks = await ImagePipeline(client=formula_client).run(
        _make_png(), image_type="image_formula"
    )
    assert formula_blocks == [
        {"type": "formula", "latex": "E=mc^2", "page": 1}
    ]

    table_client = _fake_client(
        table={
            "gpu_unavailable": False,
            "data": {"rows": [["a", "b"]], "bbox": [1, 2, 3, 4]},
            "error": None,
        }
    )
    table_blocks = await ImagePipeline(client=table_client).run(
        _make_png(), image_type="image_table"
    )
    assert table_blocks == [
        {"type": "table", "rows": [["a", "b"]], "bbox": [1, 2, 3, 4], "page": 1}
    ]


@pytest.mark.asyncio
async def test_image_pipeline_parser_output_schema(tmp_path: Path) -> None:
    client = _fake_client(
        ocr={
            "gpu_unavailable": False,
            "data": {"items": []},
            "error": None,
        }
    )
    pipeline = ImagePipeline(client=client)
    parser = ImagePipelineParser(pipeline=pipeline)
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(_make_png())
    result = await parser.parse(str(image_path))
    assert result.markdown == ""
    assert result.page_count == 1
    assert result.processing_time_ms is not None
    json_data = result.json_data
    assert json_data["schema_version"] == "1.0"
    assert json_data["file_type"] == "image"
    assert json_data["page_count"] == 1
    assert isinstance(json_data["blocks"], list)
    assert json_data["meta"]["parser"] == "image_pipeline_parser"


def test_image_pipeline_parser_registered() -> None:
    ParserRegistry._parsers.clear()
    importlib.reload(
        importlib.import_module(
            "app.parsers.implementations.image_pipeline.pipeline"
        )
    )
    for file_type in ["image", "jpg", "png", "bmp", "image_formula", "image_table"]:
        assert ParserRegistry.get_parser(file_type) is not None


def test_gpu_server_table_and_formula_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _load_server_module(
        REPO_ROOT / "gpu-pytorch" / "inference_server.py",
        "gpu_pytorch_server_b6",
    )

    class FakeTableEngine:
        def predict(self, image_path: Path) -> dict:
            return {"rows": [["a"]], "bbox": [1, 2, 3, 4]}

    monkeypatch.setattr(server, "_table_engine", FakeTableEngine())
    client = TestClient(server.app)
    image_b64 = base64.b64encode(b"fake-image").decode()
    table_response = client.post(
        "/infer",
        json={"model_type": "table", "image_base64": image_b64},
    )
    assert table_response.status_code == 200
    assert table_response.json() == {"rows": [["a"]], "bbox": [1, 2, 3, 4]}

    class MissingFormulaEngine:
        def recognize(self, image_path: Path) -> dict:
            raise server.FormulaModelNotReadyError("model missing")

    monkeypatch.setattr(server, "_formula_engine", MissingFormulaEngine())
    formula_response = client.post(
        "/infer",
        json={"model_type": "formula", "image_base64": image_b64},
    )
    assert formula_response.status_code == 501
    assert formula_response.json()["code"] == "GPU_MODEL_NOT_READY"

    class UnavailableFormulaEngine:
        def recognize(self, image_path: Path) -> dict:
            raise server.FormulaUnavailableError("gpu down")

    monkeypatch.setattr(server, "_formula_engine", UnavailableFormulaEngine())
    unavailable_response = client.post(
        "/infer",
        json={"model_type": "formula", "image_base64": image_b64},
    )
    assert unavailable_response.status_code == 503
