"""Retrieval provider implementations."""

import re
from typing import Any, Protocol

from botocore.exceptions import BotoCoreError, ClientError

from config import settings
from services.aws_clients import get_aws_clients
from utils.logging import get_logger

from .models import RetrievedDocument, RetrievalResult

LOGGER = get_logger("app.retrieval.providers")

TOKEN_STOPWORDS = {
    "about",
    "after",
    "also",
    "and",
    "are",
    "can",
    "does",
    "for",
    "from",
    "have",
    "how",
    "into",
    "need",
    "the",
    "this",
    "what",
    "when",
    "where",
    "with",
    "you",
    "your",
}


class RetrievalProvider(Protocol):
    """Interface boundary for retrieval implementations."""

    def retrieve(self, message: str, country: str, language: str, role: str, correlation_id: str) -> RetrievalResult:
        """Return approved source documents for a user question."""
        ...


def _metadata_value(metadata: dict[str, Any], *keys: str) -> str:
    """Read the first available metadata value as a string."""
    for key in keys:
        value = metadata.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _reference_score(ref: dict[str, Any]) -> float | None:
    """Extract a retrieval/reranker score from known Bedrock response shapes."""
    metadata = ref.get("metadata", {}) or {}
    candidates = [
        ref.get("score"),
        ref.get("retrievalScore"),
        ref.get("rerankerScore"),
        metadata.get("score"),
        metadata.get("retrieval_score"),
        metadata.get("retrievalScore"),
        metadata.get("reranker_score"),
        metadata.get("rerankerScore"),
    ]
    for candidate in candidates:
        try:
            if candidate is None:
                continue
            score = float(candidate)
            if 0 <= score <= 1:
                return score
            if 1 < score <= 100:
                return score / 100
        except (TypeError, ValueError):
            continue
    return None


def _tokens(text: str) -> set[str]:
    """Return meaningful lowercase tokens for lightweight local reranking."""
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2 and token not in TOKEN_STOPWORDS
    }


def _numbers(text: str) -> set[str]:
    """Return numeric values that should stay close to the user's question."""
    return set(re.findall(r"\b\d+(?:\.\d+)?(?:\s*(?:-|to)\s*\d+(?:\.\d+)?)?\b", text.lower()))


def _document_relevance(message: str, document: RetrievedDocument) -> float:
    """Score a retrieved document against the user question before prompting."""
    query_tokens = _tokens(message)
    document_text = " ".join([document.title, document.content, document.excerpt])
    document_tokens = _tokens(document_text)
    if not query_tokens or not document_tokens:
        return float(document.score or 0.0)

    overlap = len(query_tokens & document_tokens) / len(query_tokens)
    number_overlap = 0.0
    query_numbers = _numbers(message)
    if query_numbers:
        document_numbers = _numbers(document_text)
        number_overlap = len(query_numbers & document_numbers) / len(query_numbers)

    source_score = float(document.score or 0.0)
    return round((source_score * 0.55) + (overlap * 0.35) + (number_overlap * 0.10), 6)


def _rerank_documents(message: str, documents: list[RetrievedDocument]) -> list[RetrievedDocument]:
    """Prefer documents whose text best matches the exact user question."""
    return sorted(
        documents,
        key=lambda document: (
            _document_relevance(message, document),
            float(document.score or 0.0),
        ),
        reverse=True,
    )


def confidence_from_sources(sources: list[dict[str, Any]]) -> float:
    """Compute answer confidence from scores, source count, and citation quality."""
    if not sources:
        return 0.0
    scores = [float(source["score"]) for source in sources if source.get("score") is not None]
    if scores:
        top_score = max(scores)
        average_score = sum(scores) / len(scores)
        score_confidence = (top_score * 0.7) + (average_score * 0.3)
    else:
        source_count_confidence = min(len(sources), settings.BEDROCK_RETRIEVAL_RESULT_COUNT) * settings.BEDROCK_FALLBACK_SOURCE_WEIGHT
        citation_quality_count = sum(1 for source in sources if source.get("uri") and source.get("excerpt"))
        citation_quality = min(citation_quality_count, 3) * settings.BEDROCK_FALLBACK_CITATION_WEIGHT
        score_confidence = 0.45 + source_count_confidence + citation_quality
    return round(min(score_confidence, 0.99), 3)


def score_summary(sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarise source scores for retrieval quality logging."""
    scores: list[float] = []
    for source in sources:
        if source.get("score") is None:
            continue
        try:
            scores.append(float(source["score"]))
        except (TypeError, ValueError):
            continue
    return {
        "top_score": round(max(scores), 3) if scores else None,
        "average_score": round(sum(scores) / len(scores), 3) if scores else None,
        "source_count": len(sources),
    }


def source_log_summary(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return compact source details that are useful in production logs."""
    return [
        {
            "title": source.get("title", ""),
            "page": source.get("page", ""),
            "score": source.get("score"),
            "country": source.get("country", ""),
            "language": source.get("language", ""),
        }
        for source in sources[: settings.BEDROCK_RETRIEVAL_RESULT_COUNT]
    ]


class BedrockRetrievalProvider:
    """Retrieve approved source documents from Bedrock Knowledge Bases."""

    def retrieve(self, message: str, country: str, language: str, role: str, correlation_id: str) -> RetrievalResult:
        """Call the standalone Retrieve API for reliable source scores."""
        try:
            response = get_aws_clients().bedrock_agent_runtime.retrieve(
                knowledgeBaseId=settings.BEDROCK_KB_ID,
                retrievalQuery={"text": message},
                retrievalConfiguration={
                    "vectorSearchConfiguration": {
                        "numberOfResults": settings.BEDROCK_RETRIEVAL_CANDIDATE_COUNT,
                        "overrideSearchType": "HYBRID",
                        "filter": {
                            "andAll": [
                                {"equals": {"key": "country_code", "value": country}},
                                {"equals": {"key": "language", "value": language}},
                                {"equals": {"key": "status", "value": "active"}},
                            ]
                        },
                    }
                },
            )
        except (BotoCoreError, ClientError):
            LOGGER.exception("retrieval_failed", correlation_id=correlation_id, country=country, language=language, role=role)
            return RetrievalResult(documents=[], citations=[], confidence=0.0, metadata={"provider": "bedrock"})

        documents = [self._document_from_retrieve_result(result) for result in response.get("retrievalResults", [])]
        documents = [document for document in documents if document.source]
        documents = _rerank_documents(message, documents)[: settings.BEDROCK_RETRIEVAL_RESULT_COUNT]
        result = self._result(documents, provider="bedrock")
        LOGGER.info(
            "retrieval_success",
            correlation_id=correlation_id,
            country=country,
            language=language,
            role=role,
            **score_summary(result.sources),
            sources=source_log_summary(result.sources),
        )
        return result

    def _result(self, documents: list[RetrievedDocument], **metadata: Any) -> RetrievalResult:
        sources = [document.to_source() for document in documents]
        return RetrievalResult(documents=documents, citations=sources, confidence=confidence_from_sources(sources), metadata=metadata)

    def _document_from_retrieve_result(self, result: dict[str, Any]) -> RetrievedDocument:
        location = result.get("location", {})
        uri = location.get("s3Location", {}).get("uri", "")
        metadata = result.get("metadata", {}) or {}
        content = result.get("content", {}).get("text", "")
        return RetrievedDocument(
            id=_metadata_value(metadata, "id", "document_id") or uri,
            title=_metadata_value(metadata, "title", "document_title") or uri.rsplit("/", 1)[-1],
            content=content,
            source=uri,
            excerpt=content[:240],
            page=_metadata_value(metadata, "page", "page_number", "x-amz-bedrock-kb-document-page-number"),
            document_version=_metadata_value(metadata, "document_version", "version", "policy_version"),
            country=_metadata_value(metadata, "country_code", "countrycode", "country"),
            language=_metadata_value(metadata, "language", "lang"),
            score=result.get("score"),
            metadata=metadata,
        )
