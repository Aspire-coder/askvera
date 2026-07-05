"""Provider response normalization."""

from typing import Any

from app.models.responses import ModelResponse


class ResponseNormalizer:
    """Normalize provider-specific payloads into ModelResponse objects."""

    def from_bedrock_converse(
        self,
        response: dict[str, Any],
        *,
        citations: list[dict[str, Any]],
        confidence: float,
        provider: str,
        model_name: str,
        latency_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ModelResponse:
        """Normalize an Amazon Bedrock Converse response."""
        content = response.get("output", {}).get("message", {}).get("content", [])
        parts = [part.get("text", "") for part in content if isinstance(part, dict)]
        return ModelResponse(
            text="\n".join(part for part in parts if part).strip(),
            citations=citations,
            confidence=confidence,
            provider=provider,
            model_name=model_name,
            latency_ms=latency_ms,
            token_usage=response.get("usage"),
            finish_reason=response.get("stopReason", ""),
            metadata=metadata or {},
        )


response_normalizer = ResponseNormalizer()
