"""Final chat response assembly."""

from __future__ import annotations

import re
import unicodedata
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
            guardrail_intervened = model_response.finish_reason == "guardrail_intervened"
            failure_layer = (
                "aws_guardrail"
                if guardrail_intervened
                else (model_response.metadata or {}).get("failure_layer")
            )
            chat_response = ChatResponse(
                answer=model_response.text,
                # A guardrail response is safety copy, not an answer grounded in the
                # retrieved policy sections. Never present unrelated retrieval as its source.
                citations=[] if guardrail_intervened else self._supporting_citations(model_response.text, retrieval_result),
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
                    "failure_layer": failure_layer,
                    "response_source": "guardrail" if guardrail_intervened else "model",
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
                finish_reason=chat_response.metadata.get("finish_reason"),
                failure_layer=chat_response.metadata.get("failure_layer"),
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

    def fallback(
        self,
        answer: str,
        correlation_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> ChatResponse:
        """Build a canonical low-confidence fallback response."""
        chat_response = ChatResponse(
            answer=answer,
            citations=[],
            suggestions=[],
            cards=[],
            confidence=0.0,
            correlation_id=correlation_id,
            metadata={"fallback": True, "correlation_id": correlation_id, **(metadata or {})},
        )
        LOGGER.info(
            "response_builder_chat_response_built",
            correlation_id=correlation_id,
            provider="fallback",
            model_name="fallback",
            confidence=chat_response.confidence,
            source_count=0,
            response_source="fallback",
            failure_layer=chat_response.metadata.get("failure_layer"),
        )
        return chat_response

    def _supporting_citations(self, answer: str, retrieval_result: RetrievalResult) -> list[dict[str, Any]]:
        """Return only the retrieved citations that best support the answer."""
        documents = retrieval_result.documents
        if not documents:
            return []

        evidence_contract = (retrieval_result.metadata or {}).get("evidence_contract", {})
        if isinstance(evidence_contract, dict) and evidence_contract.get("status") == "accepted":
            evidence_ids = {str(identifier) for identifier in evidence_contract.get("evidence_ids", [])}
            verified = [document for document in documents if not evidence_ids or document.id in evidence_ids]
            # These documents already passed the claim-level evidence contract.
            # A second lexical check can incorrectly discard citations when the
            # answer and source use different languages.
            return [self._source_for_answer(document, answer) for document in verified[:3]]

        answer_numbers = self._numbers(answer)
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
            if self._support_score(answer, document.content or document.excerpt) >= self._minimum_support_score(answer)
            and (not answer_numbers or bool(answer_numbers & self._numbers(document.content or document.excerpt)))
        ]
        selected = supported[: 1 if answer_numbers else 2]
        return [self._source_for_answer(document, answer) for document in selected]

    def _support_score(self, answer: str, source_text: str) -> float:
        """Score how well a source text supports the final answer text."""
        answer_tokens = self._tokens(answer)
        source_tokens = self._tokens(source_text)
        if not answer_tokens or not source_tokens:
            return 0.0

        overlap = len(answer_tokens & source_tokens) / len(answer_tokens)
        answer_numbers = self._numbers(answer)
        source_numbers = self._numbers(source_text)
        number_overlap = len(answer_numbers & source_numbers) / len(answer_numbers) if answer_numbers else 0.0
        phrase_overlap = self._phrase_overlap(answer, source_text)
        return round(overlap + (number_overlap * 0.55) + (phrase_overlap * 0.25), 6)

    def _minimum_support_score(self, answer: str) -> float:
        """Require stronger source support when the answer contains measurable values."""
        return 0.35 if self._numbers(answer) else 0.12

    def _tokens(self, text: str) -> set[str]:
        """Return Unicode terms useful for citation support matching."""
        normalized = unicodedata.normalize("NFKC", text or "").casefold()
        return {
            token
            for token in re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)
            if len(token) > 3 and token not in REFERENCE_STOPWORDS
        }

    def _numbers(self, text: str) -> set[str]:
        """Return numeric values for answer/source support matching."""
        return set(re.findall(r"\b\d+(?:\.\d+)?\b", text.lower()))

    def _phrase_overlap(self, answer: str, source_text: str) -> float:
        """Reward sources that contain named concepts from the answer."""
        answer_phrases = [
            phrase.lower()
            for phrase in re.findall(
                r"\b(?:[A-Z][a-z]+|[A-Z]{2,})(?:\s+(?:[A-Z][a-z]+|[A-Z]{2,}))*\b",
                answer,
            )
            if len(phrase.split()) > 1
        ]
        if not answer_phrases:
            return 0.0
        source_lower = source_text.lower()
        return min(sum(1 for phrase in answer_phrases if phrase in source_lower) / len(answer_phrases), 1.0)

    def _source_for_answer(self, document: RetrievedDocument, answer: str) -> dict[str, Any]:
        """Build a source dictionary with an answer-focused excerpt."""
        source = document.to_source()
        source["excerpt"] = self._best_excerpt(answer, document.content or document.excerpt)
        return source

    def _best_excerpt(self, answer: str, source_text: str, length: int = 320) -> str:
        """Choose an excerpt near the strongest answer/source overlap."""
        if not source_text:
            return ""

        windows = [
            source_text[index : index + length]
            for index in range(0, max(len(source_text), 1), max(length // 2, 1))
        ] or [source_text]
        best_window = max(windows, key=lambda window: self._support_score(answer, window))
        if self._support_score(answer, best_window) <= 0:
            return source_text[:length].strip()

        return best_window.strip()


response_builder = ResponseBuilder()
