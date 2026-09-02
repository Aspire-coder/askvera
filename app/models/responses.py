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
