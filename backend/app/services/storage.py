"""Local filesystem storage service."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import aiofiles

from app.core.config import settings


class StorageService(ABC):
    """Storage abstraction for uploaded and generated files."""

    @abstractmethod
    async def save_bytes(self, relative_path: str, data: bytes) -> None:
        """Persist raw bytes at a relative path."""

    @abstractmethod
    async def save_text(self, relative_path: str, content: str) -> None:
        """Persist UTF-8 text at a relative path."""

    @abstractmethod
    async def delete(self, relative_path: str) -> None:
        """Delete a file and clean empty parent directories."""

    @abstractmethod
    async def read_bytes(self, relative_path: str) -> bytes:
        """Read raw bytes from a relative path."""


class LocalStorageService(StorageService):
    """Filesystem-backed storage rooted at settings.UPLOAD_DIR."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else Path(settings.UPLOAD_DIR)

    def _resolve(self, relative_path: str) -> Path:
        path = (self.root / relative_path).resolve()
        root = self.root.resolve()
        if not path.is_relative_to(root):
            raise ValueError("invalid storage path")
        return path

    async def save_bytes(self, relative_path: str, data: bytes) -> None:
        path = self._resolve(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, "wb") as handle:
            await handle.write(data)

    async def save_text(self, relative_path: str, content: str) -> None:
        await self.save_bytes(relative_path, content.encode("utf-8"))

    async def delete(self, relative_path: str) -> None:
        path = self._resolve(relative_path)
        if path.exists():
            path.unlink()
        current = path.parent
        root = self.root.resolve()
        while current != root and current.parent != current:
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent

    async def read_bytes(self, relative_path: str) -> bytes:
        path = self._resolve(relative_path)
        async with aiofiles.open(path, "rb") as handle:
            return await handle.read()
