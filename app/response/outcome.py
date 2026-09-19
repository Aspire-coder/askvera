"""A single typed conversation outcome, derived once per turn.

Phase 3 (docs/conversation-quality/phase3/CX_DESIGN.md) drives localized
rendering from one small, typed summary of decisions the pipeline has
*already* made -- retrieval, evidence approval and country authorization.
This module never makes any of those decisions itself: it only reads the
existing ``failure_layer`` / ``retrieval_availability`` metadata and the
existing :class:`~app.evidence.EvidenceDecision` that the orchestrator
already produced, and classifies them into one ``ConversationOutcome``.

Vocabulary discipline: the only new vocabulary this module introduces is the
``OutcomeKind`` mapping table itself. Every ``failure_layer`` value, every
``EvidenceDecision.reason`` value and the ``directory_kind`` /
``record_country`` directory fields are copied through unchanged -- never
renamed, never re-derived, never duplicated with a second alias vocabulary.

Pure by design: no I/O, no model calls, and no import of
``app.orchestrator.chat_orchestrator`` (to avoid an import cycle and to keep
this module testable with plain values).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from utils.directory_fields import _requested_directory_field_set


class OutcomeKind(str, Enum):
    """The small, closed set of conversation outcomes the CX layer renders."""

    ANSWER = "answer"
    PARTIAL_ANSWER = "partial_answer"
    CLARIFICATION = "clarification"
    EVIDENCE_MISSING = "evidence_missing"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    CROSS_MARKET_POLICY = "cross_market_policy"
    INTERNATIONAL_DIRECTORY = "international_directory"
    PERSONAL_ACCOUNT = "personal_account"
    SAFETY_REFUSAL = "safety_refusal"


# --- failure_layer -> OutcomeKind -----------------------------------------
#
# Every entry here is an existing `failure_layer` value already written by
# app/orchestrator/chat_orchestrator.py (directly as a `"failure_layer": "<x>"`
# metadata literal, or via `_governance_failure_layer` /
# `_low_confidence_failure_layer`, both of which also only ever return one of
# these exact strings) or by app/models/bedrock_provider.py, which the
# orchestrator's response metadata copies through unchanged. See
# tests/unit/test_conversation_outcome.py for the grep that keeps this table
# in sync with chat_orchestrator.py's literal `"failure_layer": "<x>"` sites.
#
#   dependency_unavailable        - retrieval/model call could not run at all
#   aws_guardrail                 - Bedrock guardrail intervened on the model
#                                    turn (also set from `guardrail_intervened`
#                                    in app/response/builder.py)
#   evidence_contract              - a generated answer failed the evidence
#                                    contract (unsupported/unapproved claim)
#   directory_source_conflict     - approved directory sources disagree and
#                                    no single value is definitive
#   candidate_narrowing_fallback  - the planner asked a narrowing question
#                                    instead of guessing among candidates
#   directory_clarification       - a directory request needs one more detail
#                                    (ambiguous reference or missing field)
#   sensitive_pii_input           - the input itself was scrubbed for privacy
#   document_period_not_covered   - the approved documents don't cover the
#                                    requested time period
#   evidence_gate                 - evidence approval declined; see
#                                    EvidenceDecision.reason for why. This is
#                                    the one failure_layer whose OutcomeKind
#                                    depends on that reason (cross-market
#                                    policy vs. plain insufficient evidence).
#   local_guardrail               - governance/risk policy blocked locally
#                                    (app.governance decision, "block" action
#                                    or the bedrock_guardrails provider)
#   risk_policy                   - governance/risk policy blocked (any other
#                                    guardrail action)
#   retrieval_miss                - no retrieval sources at all reached the
#                                    model (app/models/bedrock_provider.py)
#   low_confidence                - retrieval confidence too low to answer
#                                    (app/models/bedrock_provider.py)
_FAILURE_LAYER_KINDS: dict[str, OutcomeKind] = {
    "dependency_unavailable": OutcomeKind.DEPENDENCY_UNAVAILABLE,
    "aws_guardrail": OutcomeKind.SAFETY_REFUSAL,
    "evidence_contract": OutcomeKind.EVIDENCE_MISSING,
    "directory_source_conflict": OutcomeKind.EVIDENCE_MISSING,
    "candidate_narrowing_fallback": OutcomeKind.CLARIFICATION,
    "directory_clarification": OutcomeKind.CLARIFICATION,
    "sensitive_pii_input": OutcomeKind.SAFETY_REFUSAL,
    "document_period_not_covered": OutcomeKind.EVIDENCE_MISSING,
    "evidence_gate": OutcomeKind.EVIDENCE_MISSING,  # overridden below for cross-market
    "local_guardrail": OutcomeKind.SAFETY_REFUSAL,
    "risk_policy": OutcomeKind.SAFETY_REFUSAL,
    "retrieval_miss": OutcomeKind.EVIDENCE_MISSING,
    "low_confidence": OutcomeKind.EVIDENCE_MISSING,
}

# The one EvidenceDecision.reason that changes the OutcomeKind for a given
# failure_layer. Reused unchanged from app/evidence.py (approve_evidence);
# see EvidenceDecision.reason there for the full reason vocabulary.
_CROSS_MARKET_POLICY_REASON = "cross_market_policy_request"

# The existing directory-record marker (app/retrieval/opensearch_sections.py,
# app/orchestrator/chat_orchestrator.py) that identifies a global directory
# record answering an international-sponsoring question, as opposed to an
# ordinary per-market policy or directory document. Copied through unchanged.
_INTERNATIONAL_SPONSORING_DIRECTORY_KIND = "international_sponsoring"


@dataclass(frozen=True)
class ConversationOutcome:
    """One typed conversation outcome, attached to ChatResponse.metadata["outcome"]."""

    kind: OutcomeKind
    language: str
    country: str
    fields_requested: frozenset[str]
    fields_answered: frozenset[str]
    fields_unsupported: frozenset[str]
    directory_target: str | None
    clarification_subject: str | None
    failure_layer: str | None
    retrieval_availability: str | None

    def to_metadata(self) -> dict[str, Any]:
        """Return a JSON-safe, deterministic dict for ChatResponse.metadata["outcome"]."""
        return {
            "kind": self.kind.value,
            "language": self.language,
            "country": self.country,
            "fields_requested": sorted(self.fields_requested),
            "fields_answered": sorted(self.fields_answered),
            "fields_unsupported": sorted(self.fields_unsupported),
            "directory_target": self.directory_target,
            "clarification_subject": self.clarification_subject,
            "failure_layer": self.failure_layer,
            "retrieval_availability": self.retrieval_availability,
        }


def _is_directory_shaped(document_metadata: Mapping[str, Any]) -> bool:
    """Match the existing "is this retrieved row a directory record" check.

    Same three-field predicate app/orchestrator/chat_orchestrator.py already
    uses (directory_kind / directory_section / a directory_fields dict) --
    kept identical here rather than re-derived, per the "don't duplicate
    alias vocabularies" rule.
    """
    return bool(
        document_metadata.get("directory_kind")
        or document_metadata.get("directory_section")
        or isinstance(document_metadata.get("directory_fields"), dict)
    )


def _international_directory_target(evidence_decision: object | None) -> str | None:
    """Return the target market of an approved international-sponsoring record.

    Reads only existing evidence: the approved documents an EvidenceDecision
    already carries, and each document's existing `directory_kind` /
    `record_country` metadata. Returns None when no approved document is an
    international-sponsoring directory record (the ordinary case), so this
    never fires for a same-market directory answer or a plain policy answer.
    """
    evidence: Sequence[Any] = getattr(evidence_decision, "evidence", None) or ()
    for document in evidence:
        document_metadata: Mapping[str, Any] = getattr(document, "metadata", None) or {}
        if not _is_directory_shaped(document_metadata):
            continue
        if document_metadata.get("directory_kind") != _INTERNATIONAL_SPONSORING_DIRECTORY_KIND:
            continue
        record_country = str(document_metadata.get("record_country") or "").strip()
        return record_country or None
    return None


def _clarification_subject(failure_layer: str | None, metadata: Mapping[str, Any]) -> str | None:
    """Best-effort label for what a clarification kind is asking about.

    Only reads existing metadata already recorded alongside these two
    failure_layer values; invents nothing new.
    """
    if failure_layer == "directory_clarification":
        candidates = metadata.get("reference_candidates")
        if candidates:
            return "directory_reference"
        return "directory_field"
    if failure_layer == "candidate_narrowing_fallback":
        return "candidate_narrowing"
    return None


def derive_outcome(
    *,
    metadata: Mapping[str, Any],
    language: str,
    country: str,
    question: str,
    answer_text: str,
    evidence_decision: object | None = None,
) -> ConversationOutcome:
    """Derive the one ConversationOutcome for this turn from existing decisions.

    Pure and deterministic: same inputs always produce the same outcome, and
    nothing here calls a model, touches the network, or reads a file.

    ``evidence_decision`` is accepted as a plain object (duck-typed on
    ``.reason`` and ``.evidence``) rather than imported as a hard dependency,
    so a caller can pass ``None`` (no evidence decision was made this turn,
    e.g. a pre-retrieval fallback) or app.evidence.EvidenceDecision itself.
    """
    failure_layer = metadata.get("failure_layer")
    failure_layer = str(failure_layer) if failure_layer else None
    retrieval_availability = metadata.get("retrieval_availability")
    retrieval_availability = str(retrieval_availability) if retrieval_availability else None

    reason = getattr(evidence_decision, "reason", None)

    if failure_layer is None:
        kind = OutcomeKind.ANSWER
    elif failure_layer == "evidence_gate" and reason == _CROSS_MARKET_POLICY_REASON:
        kind = OutcomeKind.CROSS_MARKET_POLICY
    else:
        # Fail safe: an unrecognised failure_layer never becomes "answer".
        kind = _FAILURE_LAYER_KINDS.get(failure_layer, OutcomeKind.EVIDENCE_MISSING)

    directory_target = _international_directory_target(evidence_decision)
    if kind == OutcomeKind.ANSWER and directory_target is not None:
        kind = OutcomeKind.INTERNATIONAL_DIRECTORY

    requested = _requested_directory_field_set(question, language=language) or set()

    return ConversationOutcome(
        kind=kind,
        language=language,
        country=country,
        fields_requested=frozenset(requested),
        # No existing metadata records which requested fields a turn's answer
        # actually covered vs. left unsupported (see
        # scripts/capture_application_path.py's own "no field distinct from
        # runtime_scope_intent" note for the same gap on directory_target).
        # Lane 2 (app/response/partial_answer.py) owns detecting this from
        # the answer text and evidence; left empty here rather than guessed.
        fields_answered=frozenset(),
        fields_unsupported=frozenset(),
        directory_target=directory_target,
        clarification_subject=_clarification_subject(failure_layer, metadata),
        failure_layer=failure_layer,
        retrieval_availability=retrieval_availability,
    )
