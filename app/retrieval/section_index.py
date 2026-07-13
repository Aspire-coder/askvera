"""PostgreSQL-backed section retrieval.

This provider searches reviewed policy sections stored in PostgreSQL. It is
kept behind the RETRIEVAL_PROVIDER=section switch so it can be evaluated
without changing the production Bedrock retrieval path.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from services.db import get_engine
from utils.logging import get_logger

from .models import RetrievedDocument, RetrievalResult

LOGGER = get_logger("app.retrieval.section_index")

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
    "many",
    "much",
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


def _tokens(text_value: str) -> list[str]:
    """Return search-worthy lowercase tokens in source order."""
    tokens: list[str] = []
    for token in re.findall(r"[a-z0-9]+", text_value.lower()):
        if len(token) <= 2 or token in TOKEN_STOPWORDS:
            continue
        if token not in tokens:
            tokens.append(token)
    return tokens


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


def _source_score(row: dict[str, Any], message: str) -> float:
    """Blend database rank with exact title/section/text matches."""
    base_score = float(row.get("rank") or 0.0)
    section_id = str(row.get("section_id") or "").lower()
    title = str(row.get("section_title") or "").lower()
    content = str(row.get("content") or "").lower()
    search_text = str(row.get("search_text") or "").lower()
    message_lower = message.lower()
    message_tokens = set(_tokens(message))
    content_tokens = set(_tokens(search_text[:2000]))

    score = base_score
    if section_id and re.search(rf"\b{re.escape(section_id)}\b", message_lower):
        score += 0.75
    if title and title in message_lower:
        score += 0.65
    if title and all(token in message_tokens for token in _tokens(title)):
        score += 0.4
    if message_tokens:
        score += (len(message_tokens & content_tokens) / len(message_tokens)) * 0.35
    for phrase in _key_phrases(message):
        if phrase in title:
            score += 0.2
        elif phrase in content[:800]:
            score += 0.12
    return round(score, 6)


def _confidence_from_documents(documents: list[RetrievedDocument]) -> float:
    """Create a conservative confidence value from section scores."""
    if not documents:
        return 0.0
    scores = [float(document.score or 0.0) for document in documents]
    top_score = max(scores)
    avg_score = sum(scores) / len(scores)
    normalized = min((top_score * 0.75) + (avg_score * 0.25), 0.99)
    return round(normalized, 3)


class SectionSearchProvider:
    """Retrieve approved policy sections from PostgreSQL."""

    def retrieve(self, message: str, country: str, language: str, role: str, correlation_id: str) -> RetrievalResult:
        del role
        query = " ".join(_tokens(message)) or message
        like_query = f"%{query}%"
        try:
            with get_engine().connect() as connection:
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
                                metadata,
                                ts_rank_cd(
                                    to_tsvector('english', search_text),
                                    plainto_tsquery('english', :query)
                                ) AS rank
                            FROM policy_sections
                            WHERE country = :country
                              AND language = :language
                              AND (
                                to_tsvector('english', search_text) @@ plainto_tsquery('english', :query)
                                OR lower(search_text) LIKE lower(:like_query)
                              )
                        )
                        SELECT *
                        FROM ranked
                        ORDER BY rank DESC, section_id ASC
                        LIMIT :candidate_count
                        """
                    ),
                    {
                        "query": query,
                        "like_query": like_query,
                        "country": country,
                        "language": language,
                        "candidate_count": settings.SECTION_RETRIEVAL_CANDIDATE_COUNT,
                    },
                ).mappings()
                candidates = [dict(row) for row in rows]
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
                "candidate_count": len(candidates),
                "query": query,
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
        )
        return result

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
            document_version="",
            country=str(row.get("country") or ""),
            language=str(row.get("language") or ""),
            score=score,
            metadata=dict(row.get("metadata") or {}),
        )
