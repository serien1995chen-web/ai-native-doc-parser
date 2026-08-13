"""Formula recognition engine for the PyTorch GPU service."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, TypedDict


class GPUModelNotReadyError(Exception):
    """Raised when the UniMERNet model is missing."""


class GPUUnavailableError(Exception):
    """Raised when formula inference cannot run."""


FormulaResult = TypedDict("FormulaResult", {"latex": str})

TOKENIZER_FILES = (
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.json",
    "special_tokens_map.json",
)


class FormulaEngine:
    """Run UniMERNet formula recognition with lazy model loading."""

    def __init__(self, model_base: str | Path | None = None) -> None:
        self.model_base = Path(
            model_base or os.environ.get("MODEL_BASE", "/models")
        )
        self._engine: Any | None = None

    def _model_ready(self) -> bool:
        model_dir = self.model_base / "unimernet"
        if not model_dir.is_dir():
            return False
        if not (model_dir / "config.json").is_file():
            return False
        return any((model_dir / name).is_file() for name in TOKENIZER_FILES)

    @staticmethod
    def _normalize_latex(result: Any) -> str:
        if isinstance(result, dict):
            for key in ("latex", "pred", "prediction", "text"):
                if result.get(key):
                    return str(result[key])
            return str(result)
        if isinstance(result, (list, tuple)):
            return str(result[0]) if result else ""
        return str(result or "")

    def _get_engine(self) -> Any:
        if self._engine is None:
            try:
                from unimernet.infer import UniMERNet
            except Exception as exc:
                raise GPUUnavailableError(
                    f"Failed to import unimernet: {exc}"
                ) from exc
            try:
                self._engine = UniMERNet()
            except Exception as exc:
                raise GPUUnavailableError(
                    f"Failed to initialize UniMERNet: {exc}"
                ) from exc
        return self._engine

    def recognize(self, image_path: str | Path) -> FormulaResult:
        path = Path(image_path)
        if not path.is_file():
            raise GPUUnavailableError(f"Image file not found: {image_path}")
        if not self._model_ready():
            raise GPUModelNotReadyError(
                "UniMERNet model files not found under "
                f"{self.model_base / 'unimernet'}"
            )
        engine = self._get_engine()
        try:
            result = engine.predict(str(path))
        except Exception as exc:
            raise GPUUnavailableError(
                f"Formula inference failed: {exc}"
            ) from exc
        return {"latex": self._normalize_latex(result)}
