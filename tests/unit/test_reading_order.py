"""Unit tests for reading order sorting."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_reading_order() -> ModuleType:
    path = REPO_ROOT / "gpu-pytorch" / "engines" / "reading_order.py"
    spec = importlib.util.spec_from_file_location("gpu_reading_order", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(path.parent))
    return module


reading_order = _load_reading_order()
sort_regions = reading_order.sort_regions

pytestmark = pytest.mark.unit


def test_sort_regions_top_to_bottom() -> None:
    regions = [
        {"class": "text", "bbox": [0, 100, 10, 110], "confidence": 0.9},
        {"class": "text", "bbox": [0, 10, 10, 20], "confidence": 0.9},
    ]
    result = sort_regions(regions)
    assert [region["bbox"][1] for region in result] == [10, 100]


def test_sort_regions_left_to_right_within_line() -> None:
    regions = [
        {"class": "text", "bbox": [100, 10, 110, 20], "confidence": 0.9},
        {"class": "text", "bbox": [10, 10, 20, 20], "confidence": 0.9},
    ]
    result = sort_regions(regions)
    assert [region["bbox"][0] for region in result] == [10, 100]


def test_sort_regions_mixed_lines() -> None:
    regions = [
        {"class": "table", "bbox": [0, 200, 100, 220], "confidence": 0.9},
        {"class": "text", "bbox": [50, 20, 60, 30], "confidence": 0.9},
        {"class": "text", "bbox": [5, 15, 20, 25], "confidence": 0.9},
    ]
    result = sort_regions(regions)
    assert [region["class"] for region in result] == [
        "text",
        "text",
        "table",
    ]


def test_sort_regions_empty() -> None:
    assert sort_regions([]) == []


def test_sort_regions_incomplete_bbox_returns_original() -> None:
    regions = [{"class": "text", "bbox": [1, 2], "confidence": 0.9}]
    result = sort_regions(regions)
    assert result == regions
    assert result is not regions
