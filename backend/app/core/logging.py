"""JSON logging configuration."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialize a log record to compact JSON."""
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),  # noqa: UP017
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: int = logging.INFO) -> None:
    """Configure the root logger with one JSON stream handler."""
    root = logging.getLogger()
    root.setLevel(level)
    already_configured = any(
        isinstance(handler, logging.StreamHandler) and isinstance(handler.formatter, JsonFormatter)
        for handler in root.handlers
    )
    if already_configured:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
