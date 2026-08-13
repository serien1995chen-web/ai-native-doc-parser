"""Unit tests for the four-layer file type identification service."""

from __future__ import annotations

import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from app.models import File, FileIdentification
from app.services.file_type_id import FileTypeIDService


class FakeResult:
    """Minimal DB result stub."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalar_one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None


def _make_file() -> File:
    now = datetime.now(timezone.utc)
    return File(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        original_name="sample.pdf",
        uploaded_type="file",
        stored_path="2026/01/01/sample.pdf",
        file_size=4,
        status="uploaded",
        created_at=now,
        updated_at=now,
    )


def _make_db(file: File) -> AsyncMock:
    db = AsyncMock()
    db.add = Mock()
    db.execute.return_value = FakeResult([file])
    db.commit = AsyncMock()
    return db


def test_layer1_extension_mapping() -> None:
    service = FileTypeIDService()
    assert service._layer1(Path("report.pdf")).identified_type == "pdf"
    assert service._layer1(Path("app.py")).identified_type == "code"
    assert service._layer1(Path("photo.png")).identified_type == "image"
    unknown = service._layer1(Path("archive.xyz"))
    assert unknown.identified_type == "unknown"
    assert unknown.confidence == 0.0


@pytest.mark.parametrize(
    ("content", "expected_type"),
    [
        (b"%PDF-1.7\n", "pdf"),
        (b"\x89PNG\r\n\x1a\n" + b"data", "image"),
        (b"\xff\xd8\xff\xe0" + b"data", "image"),
        (b"BM" + b"data", "image"),
    ],
)
def test_layer2_magic_detection(
    tmp_path: Path,
    content: bytes,
    expected_type: str,
) -> None:
    path = tmp_path / "sample.bin"
    path.write_bytes(content + b"\x00" * 100)
    result = FileTypeIDService()._layer2(path)
    assert result.identified_type == expected_type
    assert result.confidence == 0.92


def _write_zip(tmp_path: Path, name: str, prefix: str) -> Path:
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(f"{prefix}/document.xml", "<doc/>")
    return path


@pytest.mark.parametrize(
    ("name", "prefix", "expected_type"),
    [
        ("doc.docx", "word", "docx"),
        ("book.xlsx", "xl", "xlsx"),
        ("slides.pptx", "ppt", "pptx"),
    ],
)
def test_layer2_zip_container_detection(
    tmp_path: Path,
    name: str,
    prefix: str,
    expected_type: str,
) -> None:
    path = _write_zip(tmp_path, name, prefix)
    result = FileTypeIDService()._layer2(path)
    assert result.identified_type == expected_type
    assert result.confidence == 0.92


@pytest.mark.parametrize(
    ("content", "expected_type"),
    [
        ("def hello():\n    return 1\n", "code"),
        ("<!DOCTYPE html><html><body></body></html>", "html"),
        ("# Title\n\n- item\n```python\nprint(1)\n```", "md"),
        ("just plain words", "txt"),
    ],
)
def test_layer3_content_sniffing(
    tmp_path: Path,
    content: str,
    expected_type: str,
) -> None:
    path = tmp_path / "sample.txt"
    path.write_text(content, encoding="utf-8")
    result = FileTypeIDService()._layer3(path)
    assert result.identified_type == expected_type


class FakeClassifier:
    """Deterministic Layer 4 classifier used in tests."""

    def __init__(self, detected_type: str, confidence: float) -> None:
        self.detected_type = detected_type
        self.confidence = confidence

    def classify(
        self,
        file_size: int,
        sample: bytes,
        stats: dict[str, float],
    ) -> tuple[str, float]:
        return self.detected_type, self.confidence


def test_layer4_uses_fake_classifier(tmp_path: Path) -> None:
    path = tmp_path / "binary.bin"
    path.write_bytes(b"\x00\x01\x02\x03" * 100)
    service = FileTypeIDService(layer4_classifier=FakeClassifier("code", 0.7))
    result = service._layer4(path)
    assert result.identified_type == "code"
    assert result.confidence == 0.7


@pytest.mark.asyncio
async def test_layer2_early_termination_writes_two_layers(tmp_path: Path) -> None:
    path = tmp_path / "doc.pdf"
    path.write_bytes(b"%PDF-1.7\n" + b"\x00" * 100)
    file = _make_file()
    db = _make_db(file)
    service = FileTypeIDService()

    result = await service.identify(db, file.id, path)

    assert result.identified_type == "pdf"
    assert result.final_layer == 2
    assert result.is_final is True
    assert file.identified_type == "pdf"
    assert db.add.call_count == 2
    rows = [call.args[0] for call in db.add.call_args_list]
    assert all(isinstance(row, FileIdentification) for row in rows)
    assert rows[-1].is_final is True


@pytest.mark.asyncio
async def test_layer3_early_termination(tmp_path: Path) -> None:
    path = tmp_path / "notes.md"
    path.write_text("# Title\n\nplain text", encoding="utf-8")
    file = _make_file()
    db = _make_db(file)
    service = FileTypeIDService()

    result = await service.identify(db, file.id, path)

    assert result.identified_type == "md"
    assert result.final_layer == 3
    assert db.add.call_count == 3


@pytest.mark.asyncio
async def test_all_low_confidence_returns_unknown(tmp_path: Path) -> None:
    path = tmp_path / "binary.bin"
    path.write_bytes(b"\x00\x01\x02\x03" * 100)
    file = _make_file()
    db = _make_db(file)
    service = FileTypeIDService(
        layer4_classifier=FakeClassifier("unknown", 0.2),
    )

    result = await service.identify(db, file.id, path)

    assert result.identified_type == "UNKNOWN"
    assert result.final_layer == 4
    assert file.identified_type == "UNKNOWN"
    assert file.identified_confidence == 0.2
    assert db.add.call_count == 4


@pytest.mark.asyncio
async def test_identify_updates_file_record(tmp_path: Path) -> None:
    path = tmp_path / "photo.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"data")
    file = _make_file()
    db = _make_db(file)
    service = FileTypeIDService()

    result = await service.identify(db, file.id, path)

    assert result.content_type == "image"
    assert file.identified_type == "image"
    assert file.content_type == "image"
    assert file.identified_confidence == 0.92
    db.commit.assert_awaited_once()
