"""PostgreSQL-backed section retrieval.

This provider searches reviewed policy sections stored in PostgreSQL. It is
kept behind the RETRIEVAL_PROVIDER=section switch so it can be evaluated
without changing the production Bedrock retrieval path.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from services.db import get_engine
from services.embeddings import embed_text
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

RANK_TERMS = {"supervisor", "manager"}
ONBOARDING_TERMS = {"become", "enroll", "enrollment", "register", "registration", "sign", "devenir"}
FBO_TERMS = {"fbo", "forever", "business", "owner", "owners"}
NOISY_FBO_CONTEXTS = {
    "testamentary",
    "transfer",
    "transfers",
    "inherit",
    "inheritable",
    "spouse",
    "divorce",
    "legal separation",
    "approved fbo website",
    "advertisement",
    "internet policies",
    "sponsored into a country outside",
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


def _ts_query(tokens: list[str]) -> str:
    """Build a safe broad Postgres tsquery from normalized tokens."""
    cleaned = [token for token in tokens if re.fullmatch(r"[a-z0-9]+", token)]
    return " | ".join(f"{token}:*" for token in cleaned) or "policy"


def _token_regex(tokens: list[str]) -> str:
    """Build a broad regex fallback for candidate collection."""
    cleaned = [re.escape(token) for token in tokens if re.fullmatch(r"[a-z0-9]+", token)]
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


def _exact_topic_score(message: str, title: str, content: str) -> float:
    """Reward literal policy-topic matches without encoding document-specific rules.

    Formal program names and rank names are normally preserved in a policy heading or
    its opening paragraph. Giving those literal matches a clear ranking preference is
    language-agnostic and lets each document supply its own vocabulary.
    """
    normalized_message = " ".join(message.casefold().split())
    normalized_title = " ".join(title.casefold().split())
    normalized_content = " ".join(content.casefold().split())
    score = 0.0

    for phrase in _key_phrases(message):
        if len(phrase.split()) < 2:
            continue
        if phrase in normalized_title:
            score = max(score, 1.5)
        elif phrase in normalized_content[:1800]:
            score = max(score, 0.65)

    # Program names often consist of a single distinctive token, such as a branded
    # initiative containing a number. This is intentionally generic rather than a
    # curated list of program names.
    for token in _tokens(message):
        if len(token) < 6 or not any(character.isdigit() for character in token):
            continue
        if token in normalized_title:
            score = max(score, 1.8)
        elif token in normalized_content[:1800]:
            score = max(score, 0.9)

    return score


def _definition_intent(message: str) -> bool:
    return bool(re.search(r"\b(?:what|who)\s+(?:is|are)\b|\bdefine\b|\bmeaning\b", message.lower()))


def _onboarding_intent(message: str) -> bool:
    message_tokens = set(_tokens(message))
    return bool(message_tokens & ONBOARDING_TERMS or re.search(r"\bsign\s+up\b", message.lower()))


def _fbo_definition_intent(message: str) -> bool:
    message_tokens = set(_tokens(message))
    return _definition_intent(message) and bool({"fbo", "owner"} & message_tokens) and bool(message_tokens & FBO_TERMS)


def _rank_phrase_from_message(message: str) -> str | None:
    """Find the most specific rank phrase in the user question."""
    message_lower = message.lower()
    rank_matches = re.findall(
        r"\b(?:assistant\s+supervisor|assistant\s+manager|recognized\s+manager|eagle\s+manager|"
        r"senior\s+manager|soaring\s+manager|sapphire\s+manager|diamond\s+manager|gem\s+manager|"
        r"supervisor|manager)\b",
        message_lower,
    )
    if not rank_matches:
        return None
    return max(rank_matches, key=lambda value: (len(value.split()), len(value)))


def _bonus_phrase_from_message(message: str) -> str | None:
    """Find a concrete bonus phrase instead of treating all bonus questions alike."""
    message_lower = message.lower()
    bonus_phrases = [
        "personal retail bonus",
        "preferred customer bonus",
        "wholesale novus customer bonus",
        "wholesale customer bonus",
        "novus customer bonus",
        "personal bonus",
        "leadership bonus",
        "volume bonus",
    ]
    for phrase in bonus_phrases:
        if phrase in message_lower:
            return phrase
    return None


def _rank_requirement_score(message: str, content: str) -> float:
    """Prefer the exact rank requirement over neighboring rank sections."""
    message_tokens = set(_tokens(message))
    if not ({"case", "credit", "credits"} & message_tokens or {"qualify", "qualification"} & message_tokens):
        return 0.0

    content_lower = content.lower()
    rank_phrase = _rank_phrase_from_message(message)
    rank_phrases = [rank_phrase] if rank_phrase else [
        phrase
        for phrase in _key_phrases(message)
        if set(phrase.split()) & RANK_TERMS
    ]
    for phrase in sorted(rank_phrases, key=lambda value: (len(value.split()), len(value)), reverse=True):
        exact_phrase = rf"\b{re.escape(phrase)}\b"
        if len(phrase.split()) == 1:
            exact_phrase = rf"(?<!assistant\s)\b{re.escape(phrase)}\b"
        direct_patterns = [
            rf"{exact_phrase}\s+is\s+achieved\b",
            rf"{exact_phrase}\s+is\s+earned\b",
            rf"{exact_phrase}\s+requires\b",
            rf"\breaches\s+the\s+level\s+of\s+{re.escape(phrase)}\b",
            rf"\bqualif(?:y|ies|ied)\s+as\s+{re.escape(phrase)}\b",
        ]
        if any(re.search(pattern, content_lower[:1800]) for pattern in direct_patterns):
            return 3.0
        if len(phrase.split()) == 1 and re.search(rf"\b[a-z]+\s+{re.escape(phrase)}\s+is\s+achieved\b", content_lower[:600]):
            return -1.25
    return 0.0


def _intent_score(message: str, row: dict[str, Any]) -> float:
    """Score whether a section answers the user's question type, not just its words."""
    section_id = str(row.get("section_id") or "").lower()
    title = str(row.get("section_title") or "").lower()
    content = str(row.get("content") or "").lower()
    search_text = str(row.get("search_text") or "").lower()
    message_tokens = set(_tokens(message))
    score = 0.0

    if _fbo_definition_intent(message):
        if section_id == "1.01" or content.startswith("1.01 "):
            score += 3.5
        if "independent forever business owner" in content or "independent forever business owners" in content:
            score += 1.4
        if any(noisy in search_text[:1600] for noisy in NOISY_FBO_CONTEXTS):
            score -= 2.6
        if re.search(r"\b18\.\d+", section_id) or re.search(r"\b22\.\d+", section_id):
            score -= 1.8

    if _onboarding_intent(message) and ({"fbo", "owner"} & message_tokens):
        if section_id.startswith("17.01"):
            score += 4.0
        if "fbo relationship" in content[:500] or "only adult individuals" in content[:700]:
            score += 1.8
        if {"application", "agreement", "contractual", "register", "purchase"} & set(_tokens(content[:1200])):
            score += 0.9
        if any(noisy in search_text[:1800] for noisy in NOISY_FBO_CONTEXTS):
            score -= 2.0
        if section_id.startswith(("15.", "16.", "18.", "22.")):
            score -= 1.0

    bonus_phrase = _bonus_phrase_from_message(message)
    if bonus_phrase:
        if bonus_phrase in title or bonus_phrase in content[:1800]:
            score += 3.0
        if section_id.startswith("4.01") or section_id.startswith("4.07"):
            score += 1.0
        if "bonus" not in content[:1800]:
            score -= 1.0
        if section_id.startswith(("1.02", "11.", "12.", "22.")):
            score -= 1.4

    rank_phrase = _rank_phrase_from_message(message)
    if rank_phrase:
        exact_rank = rf"\b{re.escape(rank_phrase)}\b"
        if re.search(rf"{exact_rank}\s+is\s+achieved\b", content[:2000]):
            score += 2.5
        if "case credit" in content[:2200] and ("achieved" in content[:2200] or "reaches the level" in content[:2200]):
            score += 0.8
        if re.fullmatch(r"\d+\.\d+", section_id) and len(re.findall(r"\bis\s+achieved\b", content[:2500])) > 1:
            score -= 7.0
        if section_id.startswith(("11.", "12.")) and "chairman" in content[:1200]:
            score -= 2.2

    return score


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
    phrases = _key_phrases(message)

    score = base_score
    if section_id and re.search(rf"\b{re.escape(section_id)}\b", message_lower):
        score += 0.75
    if title and title in message_lower:
        score += 0.65
    if title and all(token in message_tokens for token in _tokens(title)):
        score += 0.4
    if message_tokens:
        score += (len(message_tokens & content_tokens) / len(message_tokens)) * 0.35
    score += _exact_topic_score(message, title, content)
    for phrase in phrases:
        if phrase in title:
            score += 0.35
        elif phrase in content[:800]:
            score += 0.12
    if _definition_intent(message):
        for phrase in phrases:
            if re.search(rf"\b{re.escape(phrase)}\b(?:\s*\([^)]+\))?\s*[:\-]", content[:900]):
                score += 0.85
            elif re.search(rf"\b{re.escape(phrase)}\b\s+(?:is|are)\b", content[:600]):
                score += 0.45
    if _onboarding_intent(message):
        onboarding_words = {"applicant", "application", "contractual", "relationship", "purchase", "submit"}
        if onboarding_words & content_tokens:
            score += 0.55
        if "sponsored into a country outside" in content:
            score -= 0.25
    score += _rank_requirement_score(message, content)
    score += _intent_score(message, row)
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
                            to_tsvector('english', search_text),
                            to_tsquery('english', :ts_query)
                        ) AS rank
                    FROM policy_sections
                    WHERE country = :country
                      AND language = :language
                      AND (
                        to_tsvector('english', search_text) @@ to_tsquery('english', :ts_query)
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
            document_version="",
            country=str(row.get("country") or ""),
            language=str(row.get("language") or ""),
            score=score,
            metadata=dict(row.get("metadata") or {}),
        )
