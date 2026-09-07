"""Opt-in selector contract. Text binding is not semantic or access approval."""

from dataclasses import dataclass
import math
from typing import Sequence

from app.retrieval.source_binding import EvidenceSource, validate_support


@dataclass(frozen=True)
class BoundQuote:
    source_id: str
    quote: str


@dataclass(frozen=True)
class EvidenceDecision:
    decision: str
    draft_answer: str
    support: tuple[BoundQuote, ...]
    missing_facts: tuple[str, ...]
    confidence: float

    @property
    def source_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.source_id for item in self.support))


def validate_decision(payload: object, eligible_sources: Sequence[EvidenceSource]) -> EvidenceDecision:
    """Reject inconsistent decisions; derive citations only from validated quotes.

    No expected-answer labels, confidence thresholds or prose-based overrides.
    Caller must supply already authorized, versioned sources.
    """
    fields = {"decision", "draft_answer", "support", "missing_facts", "confidence"}
    if not isinstance(payload, dict) or set(payload) != fields:
        raise ValueError("Expected support-only decision schema")
    verdict = payload["decision"]
    if not isinstance(verdict, str) or verdict not in {
        "ANSWER_YES", "ANSWER_NO", "ANSWER_FACT", "INSUFFICIENT_EVIDENCE",
    }:
        raise ValueError("Invalid evidence verdict")
    missing = payload["missing_facts"]
    if not isinstance(missing, list) or any(not isinstance(item, str) or not item.strip() for item in missing):
        raise ValueError("Invalid missing facts")
    confidence = payload["confidence"]
    if type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError("Invalid confidence")
    draft, support = payload["draft_answer"], payload["support"]
    if not isinstance(draft, str):
        raise ValueError("Invalid draft")
    if verdict == "INSUFFICIENT_EVIDENCE":
        if draft.strip() or support != [] or not missing:
            raise ValueError("Abstention must name missing facts and contain no answer or support")
    else:
        if missing or not draft.strip():
            raise ValueError("Answer has missing required facts or no draft")
        validate_support(support, eligible_sources)
    return EvidenceDecision(verdict, draft, tuple(BoundQuote(**item) for item in support),
                            tuple(missing), float(confidence))
