"""Structured JSON logging for ASK Vera."""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

SERVICE_NAME = "ask-vera-api"


class JsonFormatter(logging.Formatter):
    """Formats log records as CloudWatch-friendly JSON."""

    def format(self, record: logging.LogRecord) -> str:
        """Return a JSON string containing standard and contextual log fields."""
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "service": SERVICE_NAME,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", "system"),
        }
        context = getattr(record, "context", None)
        if isinstance(context, dict):
            payload.update(context)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


class StructuredLogger:
    """Small adapter that keeps correlation IDs consistent."""

    def __init__(self, logger: logging.Logger) -> None:
        """Store the wrapped Python logger."""
        self._logger = logger

    def info(self, message: str, correlation_id: str = "system", **context: Any) -> None:
        """Log an informational event."""
        self._logger.info(message, extra={"correlation_id": correlation_id, "context": context})

    def warning(self, message: str, correlation_id: str = "system", **context: Any) -> None:
        """Log a warning event."""
        self._logger.warning(message, extra={"correlation_id": correlation_id, "context": context})

    def error(self, message: str, correlation_id: str = "system", **context: Any) -> None:
        """Log an error event."""
        self._logger.error(message, extra={"correlation_id": correlation_id, "context": context})

    def exception(self, message: str, correlation_id: str = "system", **context: Any) -> None:
        """Log an exception with stack trace."""
        self._logger.exception(message, extra={"correlation_id": correlation_id, "context": context})


def configure_logging() -> None:
    """Configure root logging once for JSON stdout output."""
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def get_logger(name: str) -> StructuredLogger:
    """Return a structured logger for a module."""
    if not logging.getLogger().handlers:
        configure_logging()
    return StructuredLogger(logging.getLogger(name))
