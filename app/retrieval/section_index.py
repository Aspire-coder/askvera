"""PostgreSQL-backed section retrieval.

This provider searches reviewed policy sections stored in PostgreSQL. It is
kept behind the RETRIEVAL_PROVIDER=section switch so it can be evaluated
without changing the production Bedrock retrieval path.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from services.db import get_engine
from services.embeddings import embed_text
from utils.logging import get_logger

from .models import RetrievedDocument, RetrievalResult

LOGGER = get_logger("app.retrieval.section_index")

def _tokens(text_value: str) -> list[str]:
    """Return Unicode word tokens in source order without language-specific rules."""
    tokens: list[str] = []
    normalized = unicodedata.normalize("NFKC", text_value or "").casefold()
    for token in re.findall(r"[^\W_]+", normalized, flags=re.UNICODE):
        if len(token) <= 1:
            continue
        if token not in tokens:
            tokens.append(token)
    return tokens


def _ts_query(tokens: list[str]) -> str:
    """Build a safe broad Postgres tsquery from Unicode-normalized tokens."""
    cleaned = [token.replace("'", "") for token in tokens if token and "'" not in token]
    return " | ".join(f"{token}:*" for token in cleaned) or "policy"


def _token_regex(tokens: list[str]) -> str:
    """Build a broad regex fallback for candidate collection."""
    cleaned = [re.escape(token) for token in tokens if token]
    if not cleaned:
        return r"policy"
    return r"\m(?:" + "|".join(cleaned) + r")\M"


def _key_phrases(message: str) -> list[str]:
    """Extract short phrases worth matching exactly."""
    ordered = _tokens(message)
    phrases: list[str] = []
    for size in (4, 3, 2):
        for index in range(0, max(len(ordered) - size + 1, 0)):
            phrase = " ".join(ordered[index : index + size])
            if phrase not in phrases:
                phrases.append(phrase)
    return phrases[:12]


def _normalize_text(value: str) -> str:
    """Normalize whitespace and case while retaining every language's letters."""
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    return " ".join(normalized.split())


def _character_ngrams(value: str, size: int = 3) -> set[str]:
    """Provide language-neutral lexical matching when word boundaries vary."""
    compact = "".join(character for character in _normalize_text(value) if character.isalnum())
    if len(compact) < size:
        return {compact} if compact else set()
    return {compact[index : index + size] for index in range(len(compact) - size + 1)}


def _character_overlap(left: str, right: str) -> float:
    """Measure how much of a shorter named phrase appears in the other text."""
    left_ngrams = _character_ngrams(left)
    right_ngrams = _character_ngrams(right)
    if not left_ngrams or not right_ngrams:
        return 0.0
    return len(left_ngrams & right_ngrams) / min(len(left_ngrams), len(right_ngrams))


def _exact_topic_score(message: str, title: str, content: str) -> float:
    """Reward a document's own named topic without policy-specific heuristics."""
    normalized_message = _normalize_text(message)
    normalized_title = _normalize_text(title)
    normalized_content = _normalize_text(content[:1800])
    score = 0.0

    # A section title is content-managed data. If it appears in the question, it is
    # the strongest generic evidence that this section is about the asked topic.
    if normalized_title and len(normalized_title) >= 3 and normalized_title in normalized_message:
        score += 1.6

    for phrase in _key_phrases(message):
        if phrase in normalized_title:
            score = max(score, 1.5)
        elif phrase in normalized_content:
            score = max(score, 0.65)

    for token in _tokens(message):
        if len(token) < 4 or not any(character.isdigit() for character in token):
            continue
        if token in normalized_title:
            score = max(score, 1.8)
        elif token in normalized_content:
            score = max(score, 0.9)

    return score


def _source_score(row: dict[str, Any], message: str) -> float:
    """Blend search rank with generic, document-derived lexical alignment."""
    base_score = float(row.get("rank") or 0.0)
    section_id = str(row.get("section_id") or "").lower()
    title = str(row.get("section_title") or "").lower()
    content = str(row.get("content") or "").lower()
    search_text = str(row.get("search_text") or "").lower()
    message_lower = _normalize_text(message)
    message_tokens = set(_tokens(message))
    content_tokens = set(_tokens(search_text[:2000]))
    phrases = _key_phrases(message)

    score = base_score
    if section_id and section_id in message_lower:
        score += 0.75
    if title and _normalize_text(title) in message_lower:
        score += 0.8
    title_overlap = _character_overlap(message, title)
    if title_overlap >= 0.68:
        score += title_overlap * 1.1
    if message_tokens:
        score += (len(message_tokens & content_tokens) / len(message_tokens)) * 0.35
    score += _exact_topic_score(message, title, content)
    for phrase in phrases:
        if phrase in _normalize_text(title):
            score += 0.35
        elif phrase in _normalize_text(content[:800]):
            score += 0.12
    return round(score, 6)


def _confidence_from_documents(documents: list[RetrievedDocument]) -> float:
    """Create a conservative confidence value from section scores."""
    if not documents:
        return 0.0
    scores = [float(document.score or 0.0) for document in documents]
    top_score = scores[0]
    runner_up = scores[1] if len(scores) > 1 else 0.0
    avg_score = sum(scores) / len(scores)
    margin = max(top_score - runner_up, 0.0)
    normalized = min((top_score / 10.0) + (margin / 10.0) + (avg_score / 30.0), 0.95)
    return round(normalized, 3)


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    """Return cosine similarity for two embedding vectors."""
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def _embedding_from_row(row: dict[str, Any]) -> list[float]:
    """Read an embedding stored as JSONB/list."""
    raw_embedding = row.get("embedding")
    if raw_embedding is None:
        return []
    if isinstance(raw_embedding, str):
        try:
            raw_embedding = json.loads(raw_embedding)
        except json.JSONDecodeError:
            return []
    if not isinstance(raw_embedding, list):
        return []
    return [float(value) for value in raw_embedding]


class SectionSearchProvider:
    """Retrieve approved policy sections from PostgreSQL."""

    def retrieve(self, message: str, country: str, language: str, role: str, correlation_id: str) -> RetrievalResult:
        del role
        tokens = _tokens(message)
        query = " ".join(tokens) or message
        ts_query = _ts_query(tokens)
        token_regex = _token_regex(tokens)
        try:
            with get_engine().connect() as connection:
                keyword_candidates = self._keyword_candidates(connection, ts_query, token_regex, country, language)
                keyword_best_score = self._best_candidate_score(keyword_candidates, message)
                semantic_candidates: list[dict[str, Any]] = []
                if settings.SECTION_RETRIEVAL_MODE == "hybrid":
                    semantic_candidates = self._semantic_candidates(connection, message, country, language, correlation_id)
                elif settings.SECTION_RETRIEVAL_MODE == "fallback" and self._should_use_semantic_fallback(
                    keyword_candidates,
                    keyword_best_score,
                ):
                    semantic_candidates = self._semantic_candidates(connection, message, country, language, correlation_id)
                candidates = self._merge_candidates(keyword_candidates, semantic_candidates)
        except SQLAlchemyError:
            LOGGER.exception("section_retrieval_failed", correlation_id=correlation_id, country=country, language=language)
            return RetrievalResult(documents=[], citations=[], confidence=0.0, metadata={"provider": "section"})

        scored = sorted(
            ((row, _source_score(row, message)) for row in candidates),
            key=lambda pair: pair[1],
            reverse=True,
        )
        documents = [
            self._document_from_row(row, score)
            for row, score in scored
            if score >= settings.SECTION_RETRIEVAL_MIN_SCORE
        ][: settings.SECTION_RETRIEVAL_RESULT_COUNT]
        sources = [document.to_source() for document in documents]
        result = RetrievalResult(
            documents=documents,
            citations=sources,
            confidence=_confidence_from_documents(documents),
            metadata={
                "provider": "section",
                "mode": settings.SECTION_RETRIEVAL_MODE,
                "candidate_count": len(candidates),
                "semantic_fallback_used": bool(semantic_candidates),
                "keyword_best_score": keyword_best_score,
                "query": query,
                "candidate_sources": [
                    self._document_from_row(row, score).to_source()
                    for row, score in scored[: settings.SECTION_RETRIEVAL_CANDIDATE_COUNT]
                ],
            },
        )
        LOGGER.info(
            "section_retrieval_success",
            correlation_id=correlation_id,
            country=country,
            language=language,
            source_count=len(sources),
            candidate_count=len(candidates),
            confidence=result.confidence,
            semantic_fallback_used=bool(semantic_candidates),
        )
        return result

    def _best_candidate_score(self, candidates: list[dict[str, Any]], message: str) -> float:
        """Return the best final score keyword retrieval can produce."""
        if not candidates:
            return 0.0
        return max(_source_score(row, message) for row in candidates)

    def _should_use_semantic_fallback(self, keyword_candidates: list[dict[str, Any]], keyword_best_score: float) -> bool:
        """Use semantic search only when keyword retrieval is clearly struggling."""
        if not keyword_candidates:
            return True
        return keyword_best_score < settings.SECTION_RETRIEVAL_FALLBACK_MIN_SCORE

    def _keyword_candidates(self, connection: Any, ts_query: str, token_regex: str, country: str, language: str) -> list[dict[str, Any]]:
        rows = connection.execute(
            text(
                """
                WITH ranked AS (
                    SELECT
                        id,
                        source_file,
                        source_uri,
                        country,
                        language,
                        document_type,
                        section_id,
                        section_title,
                        start_page,
                        end_page,
                        content,
                        search_text,
                        embedding,
                        metadata,
                        ts_rank_cd(
                            to_tsvector('simple', search_text),
                            to_tsquery('simple', :ts_query)
                        ) AS rank
                    FROM policy_sections
                    WHERE country = :country
                      AND language = :language
                      AND (
                        to_tsvector('simple', search_text) @@ to_tsquery('simple', :ts_query)
                        OR lower(search_text) ~ :token_regex
                      )
                )
                SELECT *
                FROM ranked
                ORDER BY rank DESC, section_id ASC
                LIMIT :candidate_count
                """
            ),
            {
                "ts_query": ts_query,
                "token_regex": token_regex,
                "country": country,
                "language": language,
                "candidate_count": settings.SECTION_RETRIEVAL_CANDIDATE_COUNT,
            },
        ).mappings()
        return [dict(row) for row in rows]

    def _semantic_candidates(
        self,
        connection: Any,
        message: str,
        country: str,
        language: str,
        correlation_id: str,
    ) -> list[dict[str, Any]]:
        try:
            query_embedding = embed_text(message)
        except Exception:
            LOGGER.exception("section_embedding_query_failed", correlation_id=correlation_id)
            return []
        if not query_embedding:
            return []

        rows = connection.execute(
            text(
                """
                SELECT
                    id,
                    source_file,
                    source_uri,
                    country,
                    language,
                    document_type,
                    section_id,
                    section_title,
                    start_page,
                    end_page,
                    content,
                    search_text,
                    embedding,
                    metadata,
                    0.0 AS rank
                FROM policy_sections
                WHERE country = :country
                  AND language = :language
                  AND embedding IS NOT NULL
                """
            ),
            {"country": country, "language": language},
        ).mappings()
        scored_rows: list[dict[str, Any]] = []
        for row in rows:
            row_dict = dict(row)
            similarity = _cosine_similarity(query_embedding, _embedding_from_row(row_dict))
            if similarity <= 0:
                continue
            row_dict["rank"] = similarity * settings.SECTION_RETRIEVAL_VECTOR_WEIGHT
            row_dict["semantic_score"] = similarity
            scored_rows.append(row_dict)
        return sorted(scored_rows, key=lambda item: float(item.get("rank") or 0.0), reverse=True)[
            : settings.SECTION_RETRIEVAL_VECTOR_CANDIDATE_COUNT
        ]

    def _merge_candidates(self, keyword_candidates: list[dict[str, Any]], semantic_candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for row in keyword_candidates + semantic_candidates:
            row_id = str(row.get("id") or "")
            if not row_id:
                continue
            existing = merged.get(row_id)
            if existing is None or float(row.get("rank") or 0.0) > float(existing.get("rank") or 0.0):
                merged[row_id] = row
        return sorted(merged.values(), key=lambda item: float(item.get("rank") or 0.0), reverse=True)[
            : max(settings.SECTION_RETRIEVAL_CANDIDATE_COUNT, settings.SECTION_RETRIEVAL_VECTOR_CANDIDATE_COUNT)
        ]

    def _document_from_row(self, row: dict[str, Any], score: float) -> RetrievedDocument:
        page = str(row.get("start_page") or "")
        end_page = row.get("end_page")
        if page and end_page and str(end_page) != page:
            page = f"{page}-{end_page}"
        source_uri = row.get("source_uri") or f"policy-section://{row.get('source_file', '')}/{row.get('section_id', '')}"
        title = f"{row.get('source_file', 'Policy')} - Sec {row.get('section_id', '')}"
        if row.get("section_title"):
            title = f"{title}: {row['section_title']}"
        content = str(row.get("content") or "")
        return RetrievedDocument(
            id=str(row.get("id") or ""),
            title=title,
            content=content,
            source=str(source_uri),
            excerpt=content[:300],
            page=page,
            document_version=str((row.get("metadata") or {}).get("document_version") or ""),
            country=str(row.get("country") or ""),
            language=str(row.get("language") or ""),
            score=score,
            metadata=dict(row.get("metadata") or {}),
        )
