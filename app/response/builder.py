"""Final chat response assembly."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from utils.logging import get_logger

from .models import ChatResponse

if TYPE_CHECKING:
    from app.models.responses import ModelResponse
    from app.retrieval.models import RetrievalResult

LOGGER = get_logger("app.response")


class ResponseBuilder:
    """Assemble canonical chat responses without calling external services."""

    def build(
        self,
        *,
        model_response: ModelResponse,
        retrieval_result: RetrievalResult,
        correlation_id: str,
        session_metadata: dict[str, Any] | None = None,
    ) -> ChatResponse:
        """Build the final internal chat response."""
        chat_response = ChatResponse(
            answer=model_response.text,
            citations=model_response.citations,
            suggestions=[],
            cards=[],
            confidence=model_response.confidence,
            correlation_id=correlation_id,
            metadata={
                "provider": model_response.provider,
                "model_name": model_response.model_name,
                "latency_ms": model_response.latency_ms,
                "token_usage": model_response.token_usage,
                "finish_reason": model_response.finish_reason,
                "retrieval_confidence": retrieval_result.confidence,
                "retrieved_document_count": len(retrieval_result.documents),
                "correlation_id": correlation_id,
                **(model_response.metadata or {}),
                **(session_metadata or {}),
            },
        )
        LOGGER.info(
            "response_builder_chat_response_built",
            correlation_id=correlation_id,
            provider=model_response.provider,
            model_name=model_response.model_name,
            confidence=model_response.confidence,
            source_count=len(model_response.citations),
            response_source=chat_response.metadata.get("cache", "model"),
        )
        return chat_response

    def from_cached(self, cached: dict[str, Any], correlation_id: str) -> ChatResponse:
        """Build a canonical response from the existing cache shape."""
        chat_response = ChatResponse(
            answer=str(cached.get("response", "")),
            citations=list(cached.get("sources", [])),
            suggestions=[],
            cards=[],
            confidence=float(cached.get("confidence", 0.0) or 0.0),
            correlation_id=correlation_id,
            metadata={"cache": "hit", "correlation_id": correlation_id},
        )
        LOGGER.info(
            "response_builder_chat_response_built",
            correlation_id=correlation_id,
            provider="cache",
            model_name="cache",
            confidence=chat_response.confidence,
            source_count=len(chat_response.citations),
            response_source="cache",
        )
        return chat_response

    def fallback(self, answer: str, correlation_id: str) -> ChatResponse:
        """Build a canonical low-confidence fallback response."""
        chat_response = ChatResponse(
            answer=answer,
            citations=[],
            suggestions=[],
            cards=[],
            confidence=0.0,
            correlation_id=correlation_id,
            metadata={"fallback": True, "correlation_id": correlation_id},
        )
        LOGGER.info(
            "response_builder_chat_response_built",
            correlation_id=correlation_id,
            provider="fallback",
            model_name="fallback",
            confidence=chat_response.confidence,
            source_count=0,
            response_source="fallback",
        )
        return chat_response


response_builder = ResponseBuilder()
