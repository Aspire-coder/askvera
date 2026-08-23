"""Evidence-bound semantic answer cache backed by Valkey sorted sets."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import time
from typing import Any

import redis

from app.retrieval.models import RetrievalResult
from config import settings
from services.cache import get_cache_client
from services.embeddings import embed_text
from utils.logging import get_logger

LOGGER = get_logger("services.semantic_cache")


@dataclass(frozen=True)
class SemanticCacheHit:
    """A safe semantic-cache match and its diagnostic measurements."""

    response: dict[str, Any]
    similarity: float
    candidates_checked: int


def semantic_cache_active() -> bool:
    """Return whether live or observe-only semantic processing is configured."""
    return bool(
        settings.SEMANTIC_CACHE_ENABLED or settings.SEMANTIC_CACHE_SHADOW_ENABLED
    )


def evidence_fingerprint(result: RetrievalResult) -> str:
    """Fingerprint the exact approved evidence available for this request."""
    documents: list[dict[str, str]] = []
    for document in result.documents:
        metadata = document.metadata or {}
        documents.append(
            {
                "id": str(document.id or ""),
                "source": str(document.source or ""),
                "version": str(document.document_version or ""),
                "content_digest": hashlib.sha256(
                    str(document.content or document.excerpt or "").encode("utf-8")
                ).hexdigest(),
                "ingestion_id": str(metadata.get("ingestion_id") or ""),
                "logical_document_id": str(metadata.get("logical_document_id") or ""),
                "section_id": str(
                    metadata.get("parent_section_id")
                    or metadata.get("section_id")
                    or ""
                ),
            }
        )
    payload = {
        "documents": sorted(
            documents, key=lambda item: json.dumps(item, sort_keys=True)
        ),
        "global_documents_searched": bool(
            (result.metadata or {}).get("global_documents_searched")
        ),
        "outline_preferred": bool((result.metadata or {}).get("outline_preferred")),
        "explicit_section_reference": str(
            (result.metadata or {}).get("explicit_section_reference") or ""
        ),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get_semantic_cache_value(
    message: str,
    country: str,
    language: str,
    role: str,
    evidence: RetrievalResult,
    correlation_id: str,
) -> SemanticCacheHit | None:
    """Return a similar answer only when its approved evidence is unchanged."""
    client = get_cache_client()
    if not semantic_cache_active() or client is None:
        return None
    try:
        query_vector = _embedding(message)
        if not query_vector:
            return None
        now = time.time()
        index_key = _namespace(country, language, role)
        client.zremrangebyscore(index_key, "-inf", now)
        entry_keys = client.zrevrangebyscore(
            index_key,
            "+inf",
            now,
            start=0,
            num=settings.SEMANTIC_CACHE_MAX_CANDIDATES,
        )
        raw_entries = client.mget(entry_keys) if entry_keys else []
        fingerprint = evidence_fingerprint(evidence)
        candidates: list[tuple[float, dict[str, Any]]] = []
        dead_keys: list[str] = []
        for entry_key, raw in zip(entry_keys, raw_entries):
            if not raw:
                dead_keys.append(entry_key)
                continue
            try:
                entry = json.loads(raw)
                if entry.get("evidence_fingerprint") != fingerprint:
                    continue
                score = _cosine_similarity(
                    query_vector, _coerce_vector(entry.get("embedding"))
                )
                response = entry.get("response")
                if isinstance(response, dict):
                    candidates.append((score, response))
            except (json.JSONDecodeError, TypeError, ValueError):
                dead_keys.append(entry_key)
        if dead_keys:
            client.zrem(index_key, *dead_keys)
        candidates.sort(key=lambda item: item[0], reverse=True)
        best_score = candidates[0][0] if candidates else 0.0
        hit = bool(candidates) and best_score >= settings.SEMANTIC_CACHE_THRESHOLD
        if hit and len(candidates) > 1:
            runner_up_score, runner_up_response = candidates[1]
            different_answer = _response_digest(candidates[0][1]) != _response_digest(
                runner_up_response
            )
            if (
                different_answer
                and best_score - runner_up_score
                < settings.SEMANTIC_CACHE_MIN_SCORE_MARGIN
            ):
                hit = False
        LOGGER.info(
            "semantic_cache_read",
            correlation_id=correlation_id,
            score=round(best_score, 4),
            hit=hit,
            candidates_checked=len(candidates),
        )
        if not hit:
            return None
        return SemanticCacheHit(candidates[0][1], best_score, len(candidates))
    except Exception as exc:  # Semantic caching is an optional fail-open optimization.
        LOGGER.warning(
            "semantic_cache_read_failed",
            correlation_id=correlation_id,
            error=type(exc).__name__,
        )
        return None


def set_semantic_cache_value(
    message: str,
    country: str,
    language: str,
    role: str,
    evidence: RetrievalResult,
    response: dict[str, Any],
    correlation_id: str,
) -> None:
    """Store one independently expiring answer without retaining question text."""
    client = get_cache_client()
    if not semantic_cache_active() or client is None:
        return
    try:
        vector = _embedding(message)
        if not vector:
            return
        now = time.time()
        expires_at = now + settings.SEMANTIC_CACHE_TTL_SECONDS
        namespace = _namespace(country, language, role)
        identity = hashlib.sha256(
            f"{evidence_fingerprint(evidence)}|{_response_digest(response)}|{time.time_ns()}".encode(
                "utf-8"
            )
        ).hexdigest()
        entry_key = f"{namespace}:entry:{identity}"
        entry = {
            "embedding": vector,
            "evidence_fingerprint": evidence_fingerprint(evidence),
            "response": response,
            "created_at": now,
            "expires_at": expires_at,
        }
        client.setex(
            entry_key,
            settings.SEMANTIC_CACHE_TTL_SECONDS,
            json.dumps(entry, separators=(",", ":")),
        )
        client.zadd(namespace, {entry_key: expires_at})
        client.expire(namespace, settings.SEMANTIC_CACHE_TTL_SECONDS)
        _trim_index(client, namespace)
        LOGGER.info(
            "semantic_cache_write",
            correlation_id=correlation_id,
            ttl=settings.SEMANTIC_CACHE_TTL_SECONDS,
        )
    except Exception as exc:  # Semantic caching is an optional fail-open optimization.
        LOGGER.warning(
            "semantic_cache_write_failed",
            correlation_id=correlation_id,
            error=type(exc).__name__,
        )


def _namespace(country: str, language: str, role: str) -> str:
    versions = "|".join(
        [
            settings.SEMANTIC_CACHE_SCHEMA_VERSION,
            settings.CACHE_SCHEMA_VERSION,
            settings.KB_VERSION,
            settings.RETRIEVAL_PIPELINE_VERSION,
            "retrieval-hardened" if settings.OPENSEARCH_RETRIEVAL_HARDENING_ENABLED else "retrieval-baseline",
            settings.CONVERSATION_ROUTING_VERSION,
            settings.RESPONSE_PIPELINE_VERSION,
            settings.PROMPT_VERSION,
            settings.BEDROCK_GUARDRAIL_VERSION,
            settings.BEDROCK_MODEL_ARN,
            settings.BEDROCK_FALLBACK_MODEL_ARN,
            settings.SEMANTIC_CACHE_EMBED_MODEL_ID,
        ]
    )
    digest = hashlib.sha256(versions.encode("utf-8")).hexdigest()[:20]
    locale = ":".join(part.strip().lower() for part in (country, language, role))
    return f"ask-vera:semantic:{locale}:{digest}"


def _embedding(message: str) -> list[float]:
    vector = embed_text(message, model_id=settings.SEMANTIC_CACHE_EMBED_MODEL_ID)
    return _coerce_vector(vector)[: settings.SEMANTIC_CACHE_MAX_VECTOR_DIMENSIONS]


def _coerce_vector(value: Any) -> list[float]:
    if not isinstance(value, list):
        return []
    return [float(item) for item in value]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def _response_digest(response: dict[str, Any]) -> str:
    answer = str(response.get("response") or "").strip()
    return hashlib.sha256(answer.encode("utf-8")).hexdigest()


def _trim_index(client: redis.Redis, namespace: str) -> None:
    excess = int(client.zcard(namespace)) - settings.SEMANTIC_CACHE_MAX_ENTRIES
    if excess <= 0:
        return
    stale_keys = client.zrange(namespace, 0, excess - 1)
    if stale_keys:
        client.delete(*stale_keys)
        client.zrem(namespace, *stale_keys)
