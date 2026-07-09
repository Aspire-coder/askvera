"""Final chat response assembly."""

from __future__ import annotations

import re
from time import perf_counter
from typing import TYPE_CHECKING, Any

from app.metrics import STAGE_RESPONSE_BUILD
from app.metrics.pipeline import record_pipeline_metric
from utils.logging import get_logger

from .models import ChatResponse

if TYPE_CHECKING:
    from app.models.responses import ModelResponse
    from app.retrieval.models import RetrievedDocument, RetrievalResult

LOGGER = get_logger("app.response")

REFERENCE_STOPWORDS = {
    "about",
    "also",
    "and",
    "answer",
    "are",
    "can",
    "does",
    "for",
    "from",
    "have",
    "into",
    "need",
    "that",
    "the",
    "this",
    "with",
    "you",
    "your",
}


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
        started = perf_counter()
        success = False
        try:
            chat_response = ChatResponse(
                answer=model_response.text,
                citations=self._supporting_citations(model_response.text, retrieval_result),
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
            success = True
            return chat_response
        finally:
            record_pipeline_metric(
                stage=STAGE_RESPONSE_BUILD,
                duration_ms=round((perf_counter() - started) * 1000, 2),
                success=success,
                correlation_id=correlation_id,
                metadata={"responseSource": "model"},
            )

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

    def _supporting_citations(self, answer: str, retrieval_result: RetrievalResult) -> list[dict[str, Any]]:
        """Return only the retrieved citations that best support the answer."""
        documents = retrieval_result.documents
        if not documents:
            return []

        ranked = sorted(
            documents,
            key=lambda document: (
                self._support_score(answer, document.content or document.excerpt),
                float(document.score or 0.0),
            ),
            reverse=True,
        )
        supported = [
            document
            for document in ranked
            if self._support_score(answer, document.content or document.excerpt) > 0
        ]
        selected = supported[:3] or ranked[: min(3, len(ranked))]
        return [self._source_for_answer(document, answer) for document in selected]

    def _support_score(self, answer: str, source_text: str) -> float:
        """Score how well a source text supports the final answer text."""
        answer_tokens = self._tokens(answer)
        source_tokens = self._tokens(source_text)
        if not answer_tokens or not source_tokens:
            return 0.0

        overlap = len(answer_tokens & source_tokens) / len(answer_tokens)
        answer_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", answer))
        source_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", source_text))
        number_overlap = len(answer_numbers & source_numbers) / len(answer_numbers) if answer_numbers else 0.0
        return round(overlap + (number_overlap * 0.5), 6)

    def _tokens(self, text: str) -> set[str]:
        """Return terms useful for citation support matching."""
        return {
            token
            for token in re.findall(r"[a-z0-9]+", text.lower())
            if len(token) > 3 and token not in REFERENCE_STOPWORDS
        }

    def _source_for_answer(self, document: RetrievedDocument, answer: str) -> dict[str, Any]:
        """Build a source dictionary with an answer-focused excerpt."""
        source = document.to_source()
        source["excerpt"] = self._best_excerpt(answer, document.content or document.excerpt)
        return source

    def _best_excerpt(self, answer: str, source_text: str, length: int = 320) -> str:
        """Choose an excerpt near the strongest answer/source overlap."""
        if not source_text:
            return ""

        source_lower = source_text.lower()
        ranked_terms = sorted(self._tokens(answer), key=len, reverse=True)
        best_index = -1
        for term in ranked_terms:
            best_index = source_lower.find(term)
            if best_index != -1:
                break

        if best_index == -1:
            return source_text[:length].strip()

        start = max(0, best_index - length // 3)
        end = min(len(source_text), start + length)
        return source_text[start:end].strip()


response_builder = ResponseBuilder()
