"""Typed response pipeline models."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ChatResponse:
    """Canonical internal chat response."""

    answer: str
    citations: list[dict[str, Any]]
    suggestions: list[dict[str, Any]]
    cards: list[dict[str, Any]]
    confidence: float | None
    metadata: dict[str, Any]
    correlation_id: str

    def to_api_result(self) -> dict[str, Any]:
        """Return the existing widget/API response shape."""
        return {
            "response": self.answer,
            "sources": self.citations,
            "confidence": self.confidence or 0.0,
            "correlationId": self.correlation_id,
            "metadata": self._public_metadata(),
        }

    def to_cache_value(self) -> dict[str, Any]:
        """Return the cache-safe response shape used by existing cache readers."""
        return {
            "response": self.answer,
            "sources": self.citations,
            "confidence": self.confidence or 0.0,
        }

    def _public_metadata(self) -> dict[str, Any]:
        """Return safe diagnostic metadata for QA without exposing internals."""
        metadata = self.metadata or {}
        public: dict[str, Any] = {}
        if metadata.get("failure_layer"):
            public["failureLayer"] = metadata["failure_layer"]
        if metadata.get("finish_reason"):
            public["finishReason"] = metadata["finish_reason"]
        if metadata.get("validation"):
            public["validation"] = metadata["validation"]
        return public
