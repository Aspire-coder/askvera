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
    routes = _conversation_routes().get(locale, {})
    response = (routes.get("responses", {}) or {}).get(category)
    return str(response).strip() if response else None


def localized_conversation_response(key: str, language: str = "") -> str | None:
    """Return controlled locale copy for a fallback or conversational response."""
    routes = _conversation_routes().get(_locale_key(language)) or _conversation_routes().get("en", {})
    response = (routes.get("responses", {}) or {}).get(key)
    return str(response).strip() if response else None


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
    enough_score = retrieval_result.confidence >= settings.BEDROCK_MIN_CONFIDENCE or top_score >= settings.SECTION_RETRIEVAL_MIN_SCORE

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
    routes = _conversation_routes().get(_locale_key(language), {})
    patterns = routes.get("patterns", {}) if isinstance(routes, dict) else {}
    for category, phrases in patterns.items():
        normalized_phrases = {_normalize_text(str(phrase)) for phrase in phrases}
        if normalized_message in normalized_phrases:
            return str(category)
    return None


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
