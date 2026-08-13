"""Four-layer cascade file type identification service."""

from __future__ import annotations

import math
import re
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import select

from app.core.config import settings
from app.models import File, FileIdentification
from app.schemas.identification import IdentificationResult

L1_EXTENSIONS = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".pptx": "pptx",
    ".xlsx": "xlsx",
    ".html": "html",
    ".htm": "html",
    ".txt": "txt",
    ".md": "md",
    ".py": "code",
    ".js": "code",
    ".ts": "code",
    ".java": "code",
    ".c": "code",
    ".cpp": "code",
    ".h": "code",
    ".go": "code",
    ".rs": "code",
    ".rb": "code",
    ".php": "code",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".bmp": "image",
    ".gif": "image",
    ".webp": "image",
}

L1_CONFIDENCE = 0.4
L2_CONFIDENCE = 0.92
L3_STRONG_CONFIDENCE = 0.85
L3_WEAK_CONFIDENCE = 0.75
L4_ACCEPTANCE_THRESHOLD = 0.5

_CODE_STRONG = re.compile(r"^\s*(def|class|import|from)\s", re.MULTILINE)
_CODE_WEAK = re.compile(r"\b(return|function|const|let|var|#include)\b")
_HTML_STRONG = re.compile(r"<!DOCTYPE|<\s*html", re.IGNORECASE)
_HTML_WEAK = re.compile(r"<\s*(div|table|body|head|p)\b", re.IGNORECASE)
_MD_STRONG = re.compile(r"^#{1,6}\s|```", re.MULTILINE)
_MD_WEAK = re.compile(r"^\s*[-*+]\s", re.MULTILINE)


@dataclass
class FinalIdentification:
    """Internal result for one pipeline layer or the final decision."""

    identified_type: str
    content_type: str | None
    confidence: float | None
    final_layer: int
    is_final: bool
    details: dict[str, Any] | None = None


class Layer4Classifier(Protocol):
    """Protocol for the heuristic fallback classifier."""

    def classify(
        self,
        file_size: int,
        sample: bytes,
        stats: dict[str, float],
    ) -> tuple[str, float]:
        """Return a candidate type and confidence."""


def _content_type_for(identified_type: str) -> str | None:
    if identified_type in {"txt", "md", "text"}:
        return "text_block"
    if identified_type == "code":
        return "code"
    if identified_type in {"image", "png", "jpg", "jpeg", "bmp", "gif", "webp"}:
        return "image"
    if identified_type == "UNKNOWN":
        return None
    return "file"


def _shannon_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = [0] * 256
    for byte in data:
        counts[byte] += 1
    length = len(data)
    return -sum(
        (count / length) * math.log2(count / length)
        for count in counts
        if count
    )


def _read_head_tail(path: Path) -> tuple[bytes, bytes]:
    with path.open("rb") as handle:
        head = handle.read(16 * 1024)
        try:
            handle.seek(-512, 2)
            tail = handle.read(512)
        except OSError:
            tail = b""
    return head, tail


def _read_text_sample(path: Path) -> str:
    with path.open("rb") as handle:
        raw = handle.read(64 * 1024)
    return raw.decode("utf-8", errors="ignore")


class HeuristicClassifier:
    """Default Layer 4 classifier using byte entropy and line statistics."""

    def classify(
        self,
        file_size: int,
        sample: bytes,
        stats: dict[str, float],
    ) -> tuple[str, float]:
        printable = sum(
            1 for byte in sample if 32 <= byte <= 126 or byte in (9, 10, 13)
        )
        printable_ratio = printable / max(len(sample), 1)
        if printable_ratio > 0.9 and stats["avg_line_length"] < 200:
            text = sample.decode("utf-8", errors="ignore")
            if stats["entropy"] > 4.2 and any(ch in text for ch in "{}();=[]"):
                return "code", 0.7
            return "text", 0.6
        return "unknown", 0.2


class FileTypeIDService:
    """Run the four-layer file type identification pipeline."""

    def __init__(self, layer4_classifier: Layer4Classifier | None = None) -> None:
        self.layer4_classifier = layer4_classifier or HeuristicClassifier()

    @staticmethod
    def _stats(sample: bytes) -> dict[str, float]:
        lines = sample.decode("utf-8", errors="ignore").splitlines()
        line_count = max(len(lines), 1)
        return {
            "entropy": _shannon_entropy(sample),
            "line_count": float(len(lines)),
            "avg_line_length": len(sample) / line_count,
        }

    def _layer1(self, file_path: Path) -> FinalIdentification:
        suffix = file_path.suffix.lower()
        detected = L1_EXTENSIONS.get(suffix, "unknown")
        confidence = L1_CONFIDENCE if detected != "unknown" else 0.0
        return FinalIdentification(
            identified_type=detected,
            content_type=_content_type_for(detected),
            confidence=confidence,
            final_layer=1,
            is_final=False,
            details={"suffix": suffix},
        )

    def _layer2(self, file_path: Path) -> FinalIdentification:
        head, tail = _read_head_tail(file_path)
        if head.startswith(b"%PDF-"):
            return self._magic_result("pdf", "file", 2, head)
        if head.startswith(b"\x89PNG\r\n\x1a\n"):
            return self._magic_result("image", "image", 2, head)
        if head.startswith(b"\xff\xd8\xff"):
            return self._magic_result("image", "image", 2, head)
        if head.startswith(b"BM"):
            return self._magic_result("image", "image", 2, head)
        if head.startswith((b"GIF87a", b"GIF89a")):
            return self._magic_result("image", "image", 2, head)
        if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
            return self._magic_result("image", "image", 2, head)
        if head.startswith(b"PK\x03\x04"):
            container_type = self._zip_container_type(file_path)
            if container_type:
                return FinalIdentification(
                    identified_type=container_type,
                    content_type="file",
                    confidence=L2_CONFIDENCE,
                    final_layer=2,
                    is_final=False,
                    details={"container": container_type},
                )
            return FinalIdentification(
                identified_type="zip",
                content_type=None,
                confidence=0.5,
                final_layer=2,
                is_final=False,
                details={"zip": "no office container marker"},
            )
        return FinalIdentification(
            identified_type="unknown",
            content_type=None,
            confidence=0.0,
            final_layer=2,
            is_final=False,
            details={"head": head[:8].hex(), "tail": tail[:8].hex()},
        )

    @staticmethod
    def _magic_result(
        identified_type: str,
        content_type: str,
        layer: int,
        head: bytes,
    ) -> FinalIdentification:
        return FinalIdentification(
            identified_type=identified_type,
            content_type=content_type,
            confidence=L2_CONFIDENCE,
            final_layer=layer,
            is_final=False,
            details={"magic": head[:8].hex()},
        )

    @staticmethod
    def _zip_container_type(file_path: Path) -> str | None:
        try:
            with zipfile.ZipFile(file_path) as archive:
                names = archive.namelist()
                if "[Content_Types].xml" not in names:
                    return None
                if any(name.startswith("word/") for name in names):
                    return "docx"
                if any(name.startswith("xl/") for name in names):
                    return "xlsx"
                if any(name.startswith("ppt/") for name in names):
                    return "pptx"
        except (zipfile.BadZipFile, OSError):
            return None
        return None

    def _layer3(self, file_path: Path) -> FinalIdentification:
        sample = _read_text_sample(file_path)
        printable = sum(
            1 for char in sample if char.isprintable() or char in "\n\r\t"
        )
        if sample and printable / len(sample) < 0.7:
            return FinalIdentification(
                identified_type="txt",
                content_type="text_block",
                confidence=0.4,
                final_layer=3,
                is_final=False,
                details={"text_features": "binary"},
            )
        if _CODE_STRONG.search(sample):
            return self._text_result("code", "code", L3_STRONG_CONFIDENCE, 3)
        if _HTML_STRONG.search(sample):
            return self._text_result("html", "file", L3_STRONG_CONFIDENCE, 3)
        if _MD_STRONG.search(sample):
            return self._text_result("md", "text_block", L3_STRONG_CONFIDENCE, 3)
        if _CODE_WEAK.search(sample):
            return self._text_result("code", "code", L3_WEAK_CONFIDENCE, 3)
        if _HTML_WEAK.search(sample):
            return self._text_result("html", "file", L3_WEAK_CONFIDENCE, 3)
        if _MD_WEAK.search(sample):
            return self._text_result("md", "text_block", L3_WEAK_CONFIDENCE, 3)
        return self._text_result("txt", "text_block", L3_STRONG_CONFIDENCE, 3)

    @staticmethod
    def _text_result(
        identified_type: str,
        content_type: str,
        confidence: float,
        layer: int,
    ) -> FinalIdentification:
        return FinalIdentification(
            identified_type=identified_type,
            content_type=content_type,
            confidence=confidence,
            final_layer=layer,
            is_final=False,
            details={"text_features": identified_type},
        )

    def _layer4(self, file_path: Path) -> FinalIdentification:
        file_size = file_path.stat().st_size if file_path.exists() else 0
        with file_path.open("rb") as handle:
            sample = handle.read(64 * 1024)
        stats = self._stats(sample)
        detected_type, confidence = self.layer4_classifier.classify(
            file_size,
            sample,
            stats,
        )
        return FinalIdentification(
            identified_type=detected_type,
            content_type=_content_type_for(detected_type),
            confidence=confidence,
            final_layer=4,
            is_final=False,
            details={"stats": stats},
        )

    async def _write_layer(
        self,
        db: Any,
        file_id: uuid.UUID,
        layer: FinalIdentification,
        is_final: bool,
    ) -> None:
        db.add(
            FileIdentification(
                id=uuid.uuid4(),
                file_id=file_id,
                layer=layer.final_layer,
                detected_type=layer.identified_type,
                confidence=layer.confidence or 0.0,
                details=layer.details,
                is_final=is_final,
            )
        )

    async def _finish(
        self,
        db: Any,
        file_id: uuid.UUID,
        final: FinalIdentification,
    ) -> IdentificationResult:
        result = await db.execute(select(File).where(File.id == file_id))
        file = result.scalar_one_or_none()
        if file is not None:
            file.identified_type = final.identified_type
            file.content_type = final.content_type
            file.identified_confidence = final.confidence
        await db.commit()
        return IdentificationResult(
            file_id=file_id,
            identified_type=final.identified_type,
            content_type=final.content_type,
            identified_confidence=final.confidence,
            final_layer=final.final_layer,
            is_final=True,
            details=final.details,
        )

    async def identify(
        self,
        db: Any,
        file_id: uuid.UUID,
        file_path: Path,
    ) -> IdentificationResult:
        """Run layers in order and persist every layer result."""
        path = Path(file_path)

        layer1 = self._layer1(path)
        layer1_final = layer1.confidence is not None and (
            layer1.confidence >= settings.L1_CONFIDENCE_THRESHOLD
        )
        await self._write_layer(db, file_id, layer1, layer1_final)
        if layer1_final:
            return await self._finish(
                db,
                file_id,
                FinalIdentification(
                    layer1.identified_type,
                    layer1.content_type,
                    layer1.confidence,
                    1,
                    True,
                    layer1.details,
                ),
            )

        layer2 = self._layer2(path)
        layer2_final = layer2.confidence is not None and (
            layer2.confidence >= settings.L2_CONFIDENCE_THRESHOLD
        )
        await self._write_layer(db, file_id, layer2, layer2_final)
        if layer2_final:
            return await self._finish(
                db,
                file_id,
                FinalIdentification(
                    layer2.identified_type,
                    layer2.content_type,
                    layer2.confidence,
                    2,
                    True,
                    layer2.details,
                ),
            )

        layer3 = self._layer3(path)
        layer3_final = layer3.confidence is not None and (
            layer3.confidence >= settings.L3_CONFIDENCE_THRESHOLD
        )
        await self._write_layer(db, file_id, layer3, layer3_final)
        if layer3_final:
            return await self._finish(
                db,
                file_id,
                FinalIdentification(
                    layer3.identified_type,
                    layer3.content_type,
                    layer3.confidence,
                    3,
                    True,
                    layer3.details,
                ),
            )

        layer4 = self._layer4(path)
        if layer4.confidence is not None and layer4.confidence >= L4_ACCEPTANCE_THRESHOLD:
            final = FinalIdentification(
                layer4.identified_type,
                layer4.content_type,
                layer4.confidence,
                4,
                True,
                layer4.details,
            )
        else:
            final = FinalIdentification(
                "UNKNOWN",
                None,
                layer4.confidence,
                4,
                True,
                layer4.details,
            )
        await self._write_layer(db, file_id, layer4, True)
        return await self._finish(db, file_id, final)
