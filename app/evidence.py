"""Evidence approval helpers for policy-grounded answers."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.retrieval.models import RetrievedDocument, RetrievalResult
from config import settings


SMALL_TALK_PATTERNS = (
    r"^\s*(hi|hello|hey|good morning|good afternoon|good evening|thanks|thank you)\s*[!.]?\s*$",
    r"^\s*(who are you|what can you help with|help|start|restart)\s*[?!.]?\s*$",
)

POLICY_SENSITIVE_TERMS = {
    "active",
    "bonus",
    "case",
    "cc",
    "credit",
    "discount",
    "earn",
    "fee",
    "fbo",
    "manager",
    "novus",
    "percentage",
    "policy",
    "qualify",
    "requirement",
    "requirements",
    "retail",
    "sponsor",
    "supervisor",
    "wholesale",
}

RULE_TERMS = {
    "achieved",
    "allowed",
    "cannot",
    "eligible",
    "generating",
    "must",
    "need",
    "prohibited",
    "qualifies",
    "qualify",
    "required",
    "requires",
    "shall",
}

STOPWORDS = {
    "about",
    "after",
    "also",
    "and",
    "anything",
    "are",
    "can",
    "does",
    "for",
    "from",
    "have",
    "how",
    "into",
    "is",
    "me",
    "my",
    "of",
    "the",
    "this",
    "to",
    "what",
    "when",
    "where",
    "who",
    "why",
    "with",
    "you",
    "your",
}


@dataclass(frozen=True)
class EvidenceDecision:
    """Decision that determines whether model generation is allowed."""

    approved: bool
    reason: str
    evidence: list[RetrievedDocument]
    query_intent: str
    exact_topic_match: bool
    direct_rule_match: bool
    top_score: float
    score_margin: float

    def to_metadata(self) -> dict[str, object]:
        """Return audit-safe metadata."""
        return {
            "approved": self.approved,
            "reason": self.reason,
            "query_intent": self.query_intent,
            "exact_topic_match": self.exact_topic_match,
            "direct_rule_match": self.direct_rule_match,
            "top_score": round(self.top_score, 6),
            "score_margin": round(self.score_margin, 6),
            "evidence_count": len(self.evidence),
            "evidence_ids": [document.id for document in self.evidence],
        }


def classify_intent(message: str) -> str:
    """Classify whether a message needs policy evidence."""
    normalized = " ".join((message or "").lower().split())
    if not normalized:
        return "empty"
    if any(re.match(pattern, normalized, flags=re.IGNORECASE) for pattern in SMALL_TALK_PATTERNS):
        return "assistant_meta"
    if any(term in _tokens(normalized) for term in POLICY_SENSITIVE_TERMS):
        return "policy_fact"
    if re.search(r"\d|%|\b(require|qualif|eligible|policy|bonus|discount|fee|sponsor|manager|supervisor)\w*", normalized):
        return "policy_fact"
    return "policy_fact"


def approve_evidence(query: str, retrieval_result: RetrievalResult, country: str, language: str) -> EvidenceDecision:
    """Approve or reject retrieved evidence before generation."""
    intent = classify_intent(query)
    documents = retrieval_result.documents
    if intent != "policy_fact":
        return EvidenceDecision(True, "non_policy_intent", documents[:1], intent, True, True, 0.0, 0.0)
    if not documents:
        return EvidenceDecision(False, "no_evidence", [], intent, False, False, 0.0, 0.0)

    top_score = float(documents[0].score or 0.0)
    second_score = float(documents[1].score or 0.0) if len(documents) > 1 else 0.0
    score_margin = top_score - second_score
    current_document = _has_current_locale_document(documents, country, language)
    exact_topic_match = _has_topic_match(query, documents[0])
    direct_rule_match = _has_direct_rule_match(query, documents[0])
    no_serious_conflict = score_margin >= -0.15
    enough_score = retrieval_result.confidence >= settings.BEDROCK_MIN_CONFIDENCE or top_score >= settings.SECTION_RETRIEVAL_MIN_SCORE

    approved = bool(current_document and enough_score and no_serious_conflict and (exact_topic_match or direct_rule_match))
    reason = "approved" if approved else "insufficient_direct_evidence"
    evidence = documents[:3] if approved else []
    return EvidenceDecision(
        approved=approved,
        reason=reason,
        evidence=evidence,
        query_intent=intent,
        exact_topic_match=exact_topic_match,
        direct_rule_match=direct_rule_match,
        top_score=top_score,
        score_margin=score_margin,
    )


def with_approved_evidence(retrieval_result: RetrievalResult, decision: EvidenceDecision) -> RetrievalResult:
    """Attach evidence decision metadata and narrow documents sent to the model."""
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
    normalized_language = (language or "").lower()
    for document in documents[:3]:
        document_country = (document.country or "").upper()
        document_language = (document.language or "").lower()
        if document_country == normalized_country and document_language in {normalized_language, "en"}:
            return True
    return False


def _has_topic_match(query: str, document: RetrievedDocument) -> bool:
    query_tokens = _meaningful_tokens(query)
    if not query_tokens:
        return True
    source_tokens = _tokens(" ".join([document.title, document.content, document.excerpt]))
    distinctive_tokens = {token for token in query_tokens if token not in STOPWORDS and len(token) >= 4}
    if not distinctive_tokens:
        return True
    overlap = distinctive_tokens & source_tokens
    return bool(overlap) and len(overlap) / len(distinctive_tokens) >= 0.2


def _has_direct_rule_match(query: str, document: RetrievedDocument) -> bool:
    query_tokens = _tokens(query)
    source_tokens = _tokens(" ".join([document.title, document.content, document.excerpt]))
    if query_tokens & {"what", "define", "definition"}:
        return bool(query_tokens & source_tokens)
    if query_tokens & {"how", "qualify", "requirement", "requirements", "eligible", "earn", "become"}:
        return bool(source_tokens & RULE_TERMS)
    return bool(query_tokens & source_tokens)


def _meaningful_tokens(text: str) -> set[str]:
    return {token for token in _tokens(text) if token not in STOPWORDS}


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))
