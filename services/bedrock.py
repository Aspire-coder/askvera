"""Bedrock Knowledge Base retrieval and generation calls."""

from typing import Any

from botocore.exceptions import BotoCoreError, ClientError, ReadTimeoutError

from config import settings
from config.vera_persona import FALLBACK_RESPONSES, SYSTEM_PROMPT_TEMPLATE, role_scope_for
from services.aws_clients import get_aws_clients
from utils.exceptions import BedrockServiceError, BedrockTimeoutError, ConfigurationError, LowConfidenceError
from utils.logging import get_logger

LOGGER = get_logger("services.bedrock")


def build_prompt(language: str, country: str, role: str, chunks: str, history: str) -> str:
    """Render the ASK Vera system prompt."""
    return (
        SYSTEM_PROMPT_TEMPLATE.replace("{{user_language}}", language)
        .replace("{{user_country}}", country)
        .replace("{{user_role}}", role)
        .replace("{{role_content_scope}}", role_scope_for(role))
        .replace("{{retrieved_chunks}}", chunks)
        .replace("{{session_history}}", history)
    )


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


def _sources_from_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for citation in response.get("citations", []):
        for ref in citation.get("retrievedReferences", []):
            location = ref.get("location", {})
            uri = location.get("s3Location", {}).get("uri") or location.get("webLocation", {}).get("url") or ""
            metadata = ref.get("metadata", {}) or {}
            if uri:
                sources.append(
                    {
                        "title": _metadata_value(metadata, "title", "document_title") or uri.rsplit("/", 1)[-1],
                        "uri": uri,
                        "excerpt": ref.get("content", {}).get("text", "")[:240],
                        "page": _metadata_value(metadata, "page", "page_number", "x-amz-bedrock-kb-document-page-number"),
                        "documentVersion": _metadata_value(metadata, "document_version", "version", "policy_version"),
                        "country": _metadata_value(metadata, "country_code", "country"),
                        "language": _metadata_value(metadata, "language", "lang"),
                        "score": _reference_score(ref),
                    }
                )
    return sources


def _confidence_from_sources(sources: list[dict[str, Any]]) -> float:
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


def retrieve_and_generate(message: str, country: str, language: str, role: str, session_history: str, correlation_id: str) -> dict[str, Any]:
    """Call Bedrock Knowledge Base with country, language, and role scoping."""
    for name in ["BEDROCK_KB_ID", "BEDROCK_MODEL_ARN", "BEDROCK_GUARDRAIL_ID", "BEDROCK_GUARDRAIL_VERSION"]:
        if getattr(settings, name).startswith("REPLACE_WITH"):
            raise ConfigurationError(f"{name} is not configured yet.")
    prompt = build_prompt(language, country, role, "$search_results$", session_history)
    params = {
        "input": {"text": message},
        "retrieveAndGenerateConfiguration": {
            "type": "KNOWLEDGE_BASE",
            "knowledgeBaseConfiguration": {
                "knowledgeBaseId": settings.BEDROCK_KB_ID,
                "modelArn": settings.BEDROCK_MODEL_ARN,
                "generationConfiguration": {
                    "promptTemplate": {"textPromptTemplate": f"{prompt}\n\nUser question: $query$"},
                    "guardrailConfiguration": {
                        "guardrailId": settings.BEDROCK_GUARDRAIL_ID,
                        "guardrailVersion": settings.BEDROCK_GUARDRAIL_VERSION,
                    },
                },
                "retrievalConfiguration": {
                    "vectorSearchConfiguration": {
                        "numberOfResults": settings.BEDROCK_RETRIEVAL_RESULT_COUNT,
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
            },
        },
    }
    try:
        response = get_aws_clients().bedrock_agent_runtime.retrieve_and_generate(**params)
    except ReadTimeoutError as exc:
        LOGGER.exception("bedrock_timeout", correlation_id=correlation_id)
        raise BedrockTimeoutError(FALLBACK_RESPONSES["bedrock_error"]) from exc
    except (BotoCoreError, ClientError) as exc:
        LOGGER.exception("bedrock_failed", correlation_id=correlation_id)
        raise BedrockServiceError(FALLBACK_RESPONSES["bedrock_error"]) from exc

    answer = response.get("output", {}).get("text", "")
    sources = _sources_from_response(response)
    confidence = _confidence_from_sources(sources)
    if confidence < settings.BEDROCK_MIN_CONFIDENCE:
        LOGGER.warning("bedrock_low_confidence", correlation_id=correlation_id, confidence=confidence)
        raise LowConfidenceError(FALLBACK_RESPONSES["low_confidence"])
    LOGGER.info("bedrock_success", correlation_id=correlation_id, source_count=len(sources), confidence=confidence)
    return {"response": answer, "sources": sources, "confidence": confidence}
