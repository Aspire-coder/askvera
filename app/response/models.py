"""Typed response pipeline models."""

from dataclasses import dataclass
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
        result = {
            "response": self.answer,
            "sources": self.citations,
            "confidence": self.confidence or 0.0,
            "correlationId": self.correlation_id,
        }
        public_metadata = self._public_metadata()
        if public_metadata:
            result["metadata"] = public_metadata
        return result

    def to_cache_value(self) -> dict[str, Any]:
        """Return the cache-safe response shape used by existing cache readers."""
        token_usage = self.metadata.get("token_usage") if isinstance(self.metadata, dict) else {}
        return {
            "response": self.answer,
            "sources": self.citations,
            "confidence": self.confidence or 0.0,
            "token_usage": dict(token_usage or {}),
            "model_name": str(self.metadata.get("model_name") or "") if isinstance(self.metadata, dict) else "",
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
        if metadata.get("client_action"):
            public["clientAction"] = metadata["client_action"]
        return public
