"""Typed model response objects."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ModelResponse:
    """Normalized response from any model provider."""

    text: str
    citations: list[dict[str, Any]]
    confidence: float
    provider: str
    model_name: str
    latency_ms: int | None = None
    token_usage: dict[str, Any] | None = None
    finish_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_chat_result(self) -> dict[str, Any]:
        """Return the existing API-compatible chat result shape."""
        return {
            "response": self.text,
            "sources": self.citations,
            "confidence": self.confidence,
        }
