"""Unit tests for GPU engines and inference server integration."""

from __future__ import annotations

import base64
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.unit


def _load_module(path: Path, module_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(path.parent))
    return module




def _load_server_module(path: Path, module_name: str) -> ModuleType:
    for key in [
        module_key
        for module_key in list(sys.modules)
        if module_key == "engines" or module_key.startswith("engines.")
    ]:
        sys.modules.pop(key, None)
    return _load_module(path, module_name)

layout_engine = _load_module(
    REPO_ROOT / "gpu-pytorch" / "engines" / "layout.py",
    "gpu_layout_engine",
)
ocr_engine = _load_module(
    REPO_ROOT / "gpu-paddle" / "engines" / "ocr.py",
    "gpu_ocr_engine",
)
pytorch_server = _load_server_module(
    REPO_ROOT / "gpu-pytorch" / "inference_server.py",
    "gpu_pytorch_server",
)
paddle_server = _load_server_module(
    REPO_ROOT / "gpu-paddle" / "inference_server.py",
    "gpu_paddle_server",
)


def test_layout_normalize_rows_maps_names_and_falls_back() -> None:
    rows = [
        [1, 2, 3, 4, 0.9, 0],
        [5, 6, 7, 8, 0.8, 1],
        [9, 10, 11, 12, 0.7, 99],
    ]
    names = {0: "Text", 1: "Table"}
    engine = layout_engine.LayoutEngine()
    assert engine._normalize_rows(rows, names) == [
        {"class": "text", "bbox": [1.0, 2.0, 3.0, 4.0], "confidence": 0.9},
        {"class": "table", "bbox": [5.0, 6.0, 7.0, 8.0], "confidence": 0.8},
        {"class": "text", "bbox": [9.0, 10.0, 11.0, 12.0], "confidence": 0.7},
    ]


def test_layout_engine_detect_with_fake_model(tmp_path: Path) -> None:
    class FakeTensor:
        def numpy(self) -> SimpleNamespace:
            return SimpleNamespace(
                tolist=lambda: [[1, 2, 3, 4, 0.95, 0]]
            )

    class FakeData:
        def cpu(self) -> FakeTensor:
            return FakeTensor()

    class FakeBoxes:
        data = FakeData()

    class FakeResult:
        boxes = FakeBoxes()
        names = {0: "Title"}

    class FakeModel:
        def predict(self, *args, **kwargs) -> list[FakeResult]:
            return [FakeResult()]

    image = tmp_path / "page.png"
    image.write_bytes(b"png")
    engine = layout_engine.LayoutEngine()
    engine._model = FakeModel()
    assert engine.detect(image) == [
        {"class": "title", "bbox": [1.0, 2.0, 3.0, 4.0], "confidence": 0.95}
    ]


def test_layout_engine_missing_file_raises() -> None:
    engine = layout_engine.LayoutEngine()
    with pytest.raises(layout_engine.GPUUnavailableError):
        engine.detect(REPO_ROOT / "no-such-file.png")


def test_ocr_engine_recognize_with_fake_ocr(tmp_path: Path) -> None:
    class FakeOCR:
        def ocr(self, path: str, cls: bool = True) -> list[list[object]]:
            return [
                [
                    [
                        [[1, 2], [3, 2], [3, 5], [1, 5]],
                        ("hello", 0.9),
                    ]
                ]
            ]

    image = tmp_path / "ocr.png"
    image.write_bytes(b"png")
    engine = ocr_engine.OCREngine()
    engine._ocr = FakeOCR()
    assert engine.recognize(image) == [
        {
            "text": "hello",
            "bbox": [1.0, 2.0, 3.0, 5.0],
            "confidence": 0.9,
        }
    ]


def test_ocr_engine_missing_file_raises() -> None:
    engine = ocr_engine.OCREngine()
    with pytest.raises(ocr_engine.GPUUnavailableError):
        engine.recognize(REPO_ROOT / "no-such-file.png")


def test_pytorch_run_layout_uses_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeLayoutEngine:
        def __init__(self) -> None:
            self.called = True

        def detect(self, image_path: Path) -> list[dict]:
            return [{"class": "text", "bbox": [1, 2, 3, 4], "confidence": 0.9}]

    monkeypatch.setattr(pytorch_server, "LayoutEngine", FakeLayoutEngine)
    assert pytorch_server._run_layout(Path("fake.png")) == {
        "detections": [
            {"class": "text", "bbox": [1, 2, 3, 4], "confidence": 0.9}
        ]
    }


def test_paddle_run_ocr_uses_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeOCREngine:
        def __init__(self) -> None:
            self.called = True

        def recognize(self, image_path: Path) -> list[dict]:
            return [{"text": "hello", "bbox": [1, 2, 3, 4], "confidence": 0.9}]

    monkeypatch.setattr(paddle_server, "OCREngine", FakeOCREngine)
    assert paddle_server._run_ocr(Path("fake.png")) == {
        "items": [{"text": "hello", "bbox": [1, 2, 3, 4], "confidence": 0.9}]
    }


def test_pytorch_run_layout_maps_model_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MissingEngine:
        def __init__(self) -> None:
            raise pytorch_server.GPUModelNotReadyError("model missing")

    monkeypatch.setattr(pytorch_server, "LayoutEngine", MissingEngine)
    with pytest.raises(HTTPException) as exc_info:
        pytorch_server._run_layout(Path("fake.png"))
    assert exc_info.value.status_code == 503


def test_paddle_run_ocr_maps_unavailable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnavailableEngine:
        def __init__(self) -> None:
            raise paddle_server.GPUUnavailableError("gpu unavailable")

    monkeypatch.setattr(paddle_server, "OCREngine", UnavailableEngine)
    with pytest.raises(HTTPException) as exc_info:
        paddle_server._run_ocr(Path("fake.png"))
    assert exc_info.value.status_code == 503


def test_pytorch_infer_layout_dispatches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeLayoutEngine:
        def __init__(self) -> None:
            pass

        def detect(self, image_path: Path) -> list[dict]:
            return [{"class": "text", "bbox": [1, 2, 3, 4], "confidence": 0.9}]

    monkeypatch.setattr(pytorch_server, "LayoutEngine", FakeLayoutEngine)
    client = TestClient(pytorch_server.app)
    image_b64 = base64.b64encode(b"fake-image").decode()
    response = client.post(
        "/infer",
        json={"model_type": "layout", "image_base64": image_b64},
    )
    assert response.status_code == 200
    assert response.json() == {
        "detections": [
            {"class": "text", "bbox": [1, 2, 3, 4], "confidence": 0.9}
        ]
    }


def test_paddle_infer_ocr_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeOCREngine:
        def __init__(self) -> None:
            pass

        def recognize(self, image_path: Path) -> list[dict]:
            return [{"text": "hello", "bbox": [1, 2, 3, 4], "confidence": 0.9}]

    monkeypatch.setattr(paddle_server, "OCREngine", FakeOCREngine)
    client = TestClient(paddle_server.app)
    image_b64 = base64.b64encode(b"fake-image").decode()
    response = client.post(
        "/infer",
        json={"model_type": "ocr", "image_base64": image_b64},
    )
    assert response.status_code == 200
    assert response.json() == {
        "items": [{"text": "hello", "bbox": [1, 2, 3, 4], "confidence": 0.9}]
    }


def test_infer_rejects_bad_model_type_and_base64() -> None:
    pytorch_client = TestClient(pytorch_server.app)
    valid_image = base64.b64encode(b"fake-image").decode()
    bad_type = pytorch_client.post(
        "/infer",
        json={"model_type": "ocr", "image_base64": valid_image},
    )
    assert bad_type.status_code == 400
    bad_base64 = pytorch_client.post(
        "/infer",
        json={"model_type": "layout", "image_base64": "%%%"},
    )
    assert bad_base64.status_code == 400

    paddle_client = TestClient(paddle_server.app)
    bad_paddle_type = paddle_client.post(
        "/infer",
        json={"model_type": "layout", "image_base64": valid_image},
    )
    assert bad_paddle_type.status_code == 400
    bad_paddle_base64 = paddle_client.post(
        "/infer",
        json={"model_type": "ocr", "image_base64": "%%%"},
    )
    assert bad_paddle_base64.status_code == 400
