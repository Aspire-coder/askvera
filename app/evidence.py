"""Evidence approval and controlled non-document routing helpers."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.retrieval.models import RetrievedDocument, RetrievalResult
from config import settings
from services.controlled_copy import localize_reviewed_copy
from services.market_config import get_document_country_codes


@dataclass(frozen=True)
class EvidenceDecision:
    """Decision that determines whether model generation is allowed."""

    approved: bool
    reason: str
    evidence: list[RetrievedDocument]
    query_intent: str
    exact_topic_match: bool
    top_score: float
    score_margin: float

    def to_metadata(self) -> dict[str, object]:
        """Return audit-safe metadata."""
        return {
            "approved": self.approved,
            "reason": self.reason,
            "query_intent": self.query_intent,
            "exact_topic_match": self.exact_topic_match,
            "top_score": round(self.top_score, 6),
            "score_margin": round(self.score_margin, 6),
            "evidence_count": len(self.evidence),
            "evidence_ids": [document.id for document in self.evidence],
        }


def classify_intent(message: str, language: str = "") -> str:
    """Route only narrowly-controlled assistant messages around document retrieval.

    Every substantive message, including unknown wording or an unsupported
    request, follows the document-grounded path and fails closed if evidence is
    insufficient. Business vocabulary does not belong in this router.
    """
    normalized = _normalize_text(message)
    if not normalized:
        return "empty"
    return "assistant_meta" if _assistant_meta_category(normalized, language) else "policy_fact"


def assistant_meta_response(message: str, language: str = "") -> str | None:
    """Return a configured response for a controlled greeting/capability message."""
    category = _assistant_meta_category(_normalize_text(message), language)
    if not category:
        return None
    locale = _locale_key(language)
    all_routes = _conversation_routes()
    routes = all_routes.get(locale, {})
    response = (routes.get("responses", {}) or {}).get(category)
    if not response:
        response = (all_routes.get("en", {}).get("responses", {}) or {}).get(category)
    return str(response).strip() if response else None


def localized_conversation_response(key: str, language: str = "") -> str | None:
    """Return controlled locale copy for a fallback or conversational response."""
    locale = _locale_key(language)
    routes = _conversation_routes()
    locale_response = ((routes.get(locale, {}).get("responses", {}) or {}).get(key))
    if locale_response:
        return str(locale_response).strip()

    english_response = ((routes.get("en", {}).get("responses", {}) or {}).get(key))
    source = str(english_response).strip() if english_response else ""
    if not source or locale == "en":
        return source or None
    return localize_reviewed_copy(source, locale, key) or source


def approve_evidence(query: str, retrieval_result: RetrievalResult, country: str, language: str) -> EvidenceDecision:
    """Approve approved, current-locale evidence before model generation."""
    intent = classify_intent(query, language)
    documents = retrieval_result.documents
    if intent != "policy_fact":
        return EvidenceDecision(True, "non_document_intent", documents[:1], intent, True, 0.0, 0.0)
    if not documents:
        return EvidenceDecision(False, "no_evidence", [], intent, False, 0.0, 0.0)

    top_score = float(documents[0].score or 0.0)
    second_score = float(documents[1].score or 0.0) if len(documents) > 1 else 0.0
    score_margin = top_score - second_score
    current_document = _has_current_locale_document(documents, country, language)
    exact_topic_match = any(_has_topic_match(query, document) for document in documents)
    enough_score = retrieval_result.confidence >= settings.BEDROCK_MIN_CONFIDENCE or (
        retrieval_result.confidence >= settings.BEDROCK_CONFIDENCE_EVIDENCE_MIN_CONFIDENCE
        and top_score >= settings.SECTION_RETRIEVAL_MIN_SCORE
    ) or bool(retrieval_result.metadata.get("strong_local_match"))

    # Safety is based on approved document metadata and retrieval confidence,
    # not an English list of business or rule words. Topic overlap is retained
    # only for diagnostics and retrieval-quality monitoring.
    approved = bool(current_document and enough_score)
    reason = "approved" if approved else "insufficient_approved_evidence"
    # The retrieval provider has already bounded this reviewed evidence set. Keeping
    # it intact avoids dropping the governing section merely because it ranked fourth
    # before the optional evidence selector is applied.
    evidence = documents if approved else []
    return EvidenceDecision(
        approved=approved,
        reason=reason,
        evidence=evidence,
        query_intent=intent,
        exact_topic_match=exact_topic_match,
        top_score=top_score,
        score_margin=score_margin,
    )


def with_approved_evidence(retrieval_result: RetrievalResult, decision: EvidenceDecision) -> RetrievalResult:
    """Attach decision metadata and narrow the model context to approved sections."""
    documents = decision.evidence if decision.approved else []
    return RetrievalResult(
        documents=documents,
        citations=[document.to_source() for document in documents],
        confidence=retrieval_result.confidence,
        metadata={
            **(retrieval_result.metadata or {}),
            "evidence_decision": decision.to_metadata(),
        },
    )


def _has_current_locale_document(documents: list[RetrievedDocument], country: str, language: str) -> bool:
    normalized_country = (country or "").upper()
    allowed_countries = get_document_country_codes(normalized_country)
    normalized_language = _locale_key(language)
    allowed_languages = {normalized_language}
    if settings.OPENSEARCH_ALLOW_ENGLISH_FALLBACK:
        allowed_languages.add("en")
    for document in documents:
        if str(document.metadata.get("access_scope") or "").lower() == "global":
            return True
        document_country = (document.country or "").upper()
        document_language = _locale_key(document.language)
        if document_country in allowed_countries and document_language in allowed_languages:
            return True
    return False


def _has_topic_match(query: str, document: RetrievedDocument) -> bool:
    """Provide a Unicode-safe lexical diagnostic without deciding answer safety."""
    query_tokens = _tokens(query)
    source_tokens = _tokens(" ".join([document.title, document.content, document.excerpt]))
    if not query_tokens or not source_tokens:
        return False
    overlap = query_tokens & source_tokens
    return bool(overlap) and len(overlap) / len(query_tokens) >= 0.2


@lru_cache(maxsize=1)
def _conversation_routes() -> dict[str, dict[str, Any]]:
    """Load small-talk routing from reviewed locale configuration."""
    path = Path(settings.CONVERSATION_ROUTES_PATH)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    locales = payload.get("locales", {})
    return locales if isinstance(locales, dict) else {}


def _assistant_meta_category(normalized_message: str, language: str) -> str | None:
    if not normalized_message:
        return None
    all_routes = _conversation_routes()
    locale = _locale_key(language)
    route_candidates = [all_routes.get(locale, {})]
    # English reviewed phrases are safe to recognize in every market. This
    # keeps English-language widget traffic consistent even when the market's
    # configured default language is different.
    if locale != "en":
        route_candidates.append(all_routes.get("en", {}))
    # Recognize reviewed greetings regardless of the selected response locale.
    # This supports visitors who greet AskVera in another configured language,
    # while the response itself remains in the selected widget language.
    route_candidates.extend(
        routes
        for candidate_locale, routes in all_routes.items()
        if candidate_locale not in {locale, "en"}
    )
    for routes in route_candidates:
        patterns = routes.get("patterns", {}) if isinstance(routes, dict) else {}
        phrase_entries: list[tuple[tuple[str, ...], str]] = []
        for category, phrases in patterns.items():
            normalized_phrases = {_normalize_text(str(phrase)) for phrase in phrases}
            if normalized_message in normalized_phrases:
                return str(category)
            if any(
                _safe_short_phrase_variant(normalized_message, phrase, str(category))
                for phrase in normalized_phrases
            ):
                return str(category)
            phrase_entries.extend(
                (tuple(phrase.split()), str(category))
                for phrase in normalized_phrases
                if phrase
            )
        composed_category = _composed_assistant_meta_category(normalized_message, phrase_entries)
        if composed_category:
            return composed_category
    return None


def _safe_short_phrase_variant(message: str, phrase: str, category: str) -> bool:
    """Allow only tightly bounded typos for reviewed social phrases."""
    if category not in {"greeting", "thanks", "farewell"}:
        return False
    if not message or not phrase or len(message.split()) > 3 or len(message) > 32:
        return False
    compact_message = message.replace(" ", "")
    compact_phrase = phrase.replace(" ", "")
    if compact_message == compact_phrase:
        return True
    if min(len(compact_message), len(compact_phrase)) < 3:
        return False
    if compact_message[:1] != compact_phrase[:1]:
        return False
    return _edit_distance_at_most_one(compact_message, compact_phrase)


def _edit_distance_at_most_one(left: str, right: str) -> bool:
    """Return true for one insertion, deletion, substitution, or transposition."""
    if left == right:
        return True
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        differences = [index for index, pair in enumerate(zip(left, right)) if pair[0] != pair[1]]
        if len(differences) == 1:
            return True
        return (
            len(differences) == 2
            and differences[1] == differences[0] + 1
            and left[differences[0]] == right[differences[1]]
            and left[differences[1]] == right[differences[0]]
        )
    shorter, longer = (left, right) if len(left) < len(right) else (right, left)
    short_index = 0
    long_index = 0
    skipped = False
    while short_index < len(shorter) and long_index < len(longer):
        if shorter[short_index] == longer[long_index]:
            short_index += 1
            long_index += 1
            continue
        if skipped:
            return False
        skipped = True
        long_index += 1
    return True


def _composed_assistant_meta_category(
    normalized_message: str,
    phrase_entries: list[tuple[tuple[str, ...], str]],
) -> str | None:
    """Recognize messages made entirely from two or three reviewed phrases."""
    message_tokens = tuple(normalized_message.split())
    if not message_tokens:
        return None
    entries = sorted(phrase_entries, key=lambda item: len(item[0]), reverse=True)
    joiners = {"and", "askvera", "please", "vera"}

    def match_from(index: int, categories: tuple[str, ...]) -> tuple[str, ...] | None:
        if index == len(message_tokens):
            return categories if len(categories) >= 2 else None
        if len(categories) >= 3:
            return None
        if categories and message_tokens[index] in joiners:
            joined = match_from(index + 1, categories)
            if joined:
                return joined
        for phrase_tokens, category in entries:
            end = index + len(phrase_tokens)
            if message_tokens[index:end] == phrase_tokens:
                matched = match_from(end, (*categories, category))
                if matched:
                    return matched
        return None

    categories = match_from(0, ())
    return categories[-1] if categories else None


def _locale_key(language: str) -> str:
    """Use the primary language tag for locale configuration and metadata checks."""
    return (language or "en").split("-", 1)[0].lower()


def _normalize_text(value: str) -> str:
    """Case-fold text while preserving accented and non-Latin letters."""
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    return " ".join("".join(character if character.isalnum() else " " for character in normalized).split())


def _tokens(text: str) -> set[str]:
    """Return Unicode word tokens suitable for non-authoritative diagnostics."""
    return {
        token
        for token in re.findall(r"[^\W_]+", _normalize_text(text), flags=re.UNICODE)
        if len(token) >= 3 and not token.isdigit()
    }
