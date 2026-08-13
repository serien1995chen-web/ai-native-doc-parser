"""Unit tests for PaddleOCR result normalization."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PADDLE_SERVER = REPO_ROOT / "gpu-paddle" / "engines" / "ocr.py"


def _load_paddle_server() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "gpu_paddle_server", PADDLE_SERVER
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


paddle_server = _load_paddle_server()
normalize_ocr_result = paddle_server._normalize_ocr_result

pytestmark = pytest.mark.unit


def test_normalize_ocr_result_list_nested_polygon() -> None:
    result: list[Any] = [
        [
            [
                [[1, 2], [3, 2], [3, 5], [1, 5]],
                ("hello", 0.9),
            ]
        ]
    ]
    assert normalize_ocr_result(result) == {
        "items": [
            {
                "text": "hello",
                "bbox": [1.0, 2.0, 3.0, 5.0],
                "confidence": 0.9,
            }
        ]
    }


def test_normalize_ocr_result_list_flat_bbox() -> None:
    result: list[Any] = [
        [
            [
                [10, 20, 30, 40],
                ("flat", 0.8),
            ]
        ]
    ]
    assert normalize_ocr_result(result) == {
        "items": [
            {
                "text": "flat",
                "bbox": [10.0, 20.0, 30.0, 40.0],
                "confidence": 0.8,
            }
        ]
    }


def test_normalize_ocr_result_dict_text_bbox_confidence() -> None:
    result = {
        "text": "world",
        "bbox": [1, 2, 3, 4],
        "confidence": 0.7,
    }
    assert normalize_ocr_result(result) == {
        "items": [
            {
                "text": "world",
                "bbox": [1.0, 2.0, 3.0, 4.0],
                "confidence": 0.7,
            }
        ]
    }


def test_normalize_ocr_result_dict_points_score() -> None:
    result = {
        "text": "abc",
        "points": [[0, 0], [2, 0], [2, 3], [0, 3]],
        "score": 0.6,
    }
    assert normalize_ocr_result(result) == {
        "items": [
            {
                "text": "abc",
                "bbox": [0.0, 0.0, 2.0, 3.0],
                "confidence": 0.6,
            }
        ]
    }


def test_normalize_ocr_result_rec_batch_keys() -> None:
    result = {
        "rec_texts": ["a", "b"],
        "rec_scores": [0.9, 0.8],
        "rec_polys": [
            [[0, 0], [1, 0], [1, 1], [0, 1]],
            [[2, 2], [3, 2], [3, 3], [2, 3]],
        ],
    }
    assert normalize_ocr_result(result) == {
        "items": [
            {
                "text": "a",
                "bbox": [0.0, 0.0, 1.0, 1.0],
                "confidence": 0.9,
            },
            {
                "text": "b",
                "bbox": [2.0, 2.0, 3.0, 3.0],
                "confidence": 0.8,
            },
        ]
    }


def test_normalize_ocr_result_empty_and_unparseable() -> None:
    assert normalize_ocr_result([]) == {"items": []}
    assert normalize_ocr_result({}) == {"items": []}
    assert normalize_ocr_result([[123]]) == {"items": []}
