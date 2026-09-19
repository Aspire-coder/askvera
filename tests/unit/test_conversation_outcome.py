"""Tests for app.response.outcome: the pure ConversationOutcome derivation.

These tests drive the failure_layer -> OutcomeKind mapping from the actual
source of `"failure_layer": "<x>"` literals in chat_orchestrator.py, so a new
failure_layer added there without a corresponding entry in
app.response.outcome._FAILURE_LAYER_KINDS fails this suite instead of
silently falling through.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.response.outcome import (
    ConversationOutcome,
    OutcomeKind,
    _FAILURE_LAYER_KINDS,
    derive_outcome,
)

_ORCHESTRATOR_PATH = (
    Path(__file__).resolve().parents[2] / "app" / "orchestrator" / "chat_orchestrator.py"
)

# failure_layer values that reach chat_orchestrator.py's response metadata
# only through a helper method's `return "<literal>"` (not the inline
# `"failure_layer": "<x>"` dict-literal form the grep below looks for).
# Found by reading _governance_failure_layer, _low_confidence_failure_layer
# and app/models/bedrock_provider.py directly: see app/response/outcome.py's
# module docstring table for the source of each one.
_INDIRECT_FAILURE_LAYERS = {"local_guardrail", "risk_policy", "retrieval_miss", "low_confidence"}


def _failure_layer_literals_in_orchestrator() -> set[str]:
    """Every `"failure_layer": "<literal>"` value written in chat_orchestrator.py."""
    source = _ORCHESTRATOR_PATH.read_text(encoding="utf-8")
    return set(re.findall(r'"failure_layer":\s*"([^"]+)"', source))


class _FakeDocument:
    def __init__(self, metadata: dict) -> None:
        self.metadata = metadata


class _FakeEvidenceDecision:
    def __init__(self, reason: str = "approved", evidence: list | None = None) -> None:
        self.reason = reason
        self.evidence = evidence or []


def test_orchestrator_source_has_failure_layer_literals_to_check() -> None:
    # A sanity check on the grep itself: if this ever comes back empty, the
    # regex or the file path broke silently instead of exercising anything.
    assert len(_failure_layer_literals_in_orchestrator()) >= 8


def test_every_orchestrator_failure_layer_literal_is_mapped() -> None:
    """A new failure_layer literal added to chat_orchestrator.py without a
    mapping entry here must fail this test, not silently map to evidence_missing."""
    literals = _failure_layer_literals_in_orchestrator()
    unmapped = literals - set(_FAILURE_LAYER_KINDS)
    assert not unmapped, (
        f"chat_orchestrator.py now sets failure_layer to {sorted(unmapped)}, "
        "which app.response.outcome._FAILURE_LAYER_KINDS does not map. "
        "Add an entry (see the mapping table's comment for the existing ones)."
    )


def test_every_known_failure_layer_value_maps_to_exactly_one_kind() -> None:
    all_known_layers = _failure_layer_literals_in_orchestrator() | _INDIRECT_FAILURE_LAYERS
    for layer in sorted(all_known_layers):
        outcome = derive_outcome(
            metadata={"failure_layer": layer},
            language="en",
            country="US",
            question="What is the phone number?",
            answer_text="",
        )
        assert isinstance(outcome.kind, OutcomeKind)
        assert outcome.failure_layer == layer


def test_dependency_unavailable_layer_maps_to_dependency_unavailable_kind() -> None:
    outcome = derive_outcome(
        metadata={"failure_layer": "dependency_unavailable", "retrieval_availability": "unavailable"},
        language="en",
        country="US",
        question="What is the delivery cost?",
        answer_text="",
    )
    assert outcome.kind is OutcomeKind.DEPENDENCY_UNAVAILABLE
    assert outcome.retrieval_availability == "unavailable"
    assert outcome.failure_layer == "dependency_unavailable"


def test_dependency_unavailable_carries_retrieval_availability_when_absent_too() -> None:
    outcome = derive_outcome(
        metadata={"failure_layer": "dependency_unavailable"},
        language="en",
        country="US",
        question="What is the delivery cost?",
        answer_text="",
    )
    assert outcome.kind is OutcomeKind.DEPENDENCY_UNAVAILABLE
    assert outcome.retrieval_availability is None


def test_cross_market_policy_reason_overrides_evidence_gate_layer() -> None:
    decision = _FakeEvidenceDecision(reason="cross_market_policy_request")
    outcome = derive_outcome(
        metadata={"failure_layer": "evidence_gate"},
        language="en",
        country="US",
        question="What is the company policy in France?",
        answer_text="",
        evidence_decision=decision,
    )
    assert outcome.kind is OutcomeKind.CROSS_MARKET_POLICY
    assert outcome.failure_layer == "evidence_gate"


def test_evidence_gate_without_cross_market_reason_maps_to_evidence_missing() -> None:
    decision = _FakeEvidenceDecision(reason="insufficient_approved_evidence")
    outcome = derive_outcome(
        metadata={"failure_layer": "evidence_gate"},
        language="en",
        country="US",
        question="What is the minimum order size?",
        answer_text="",
        evidence_decision=decision,
    )
    assert outcome.kind is OutcomeKind.EVIDENCE_MISSING


def test_evidence_gate_with_no_evidence_decision_maps_to_evidence_missing() -> None:
    outcome = derive_outcome(
        metadata={"failure_layer": "evidence_gate"},
        language="en",
        country="US",
        question="What is the minimum order size?",
        answer_text="",
    )
    assert outcome.kind is OutcomeKind.EVIDENCE_MISSING


def test_clean_answer_with_no_failure_layer_maps_to_answer() -> None:
    outcome = derive_outcome(
        metadata={},
        language="en",
        country="US",
        question="What is the return policy?",
        answer_text="You may return products within 30 days.",
    )
    assert outcome.kind is OutcomeKind.ANSWER
    assert outcome.failure_layer is None


def test_unknown_failure_layer_fails_safe_to_evidence_missing_never_answer() -> None:
    outcome = derive_outcome(
        metadata={"failure_layer": "a_future_layer_nobody_mapped_yet"},
        language="en",
        country="US",
        question="What is the return policy?",
        answer_text="",
    )
    assert outcome.kind is OutcomeKind.EVIDENCE_MISSING
    assert outcome.kind is not OutcomeKind.ANSWER
    assert outcome.failure_layer == "a_future_layer_nobody_mapped_yet"


def test_international_sponsoring_directory_record_sets_international_directory_kind() -> None:
    document = _FakeDocument(
        {
            "directory_kind": "international_sponsoring",
            "record_country": "France",
        }
    )
    decision = _FakeEvidenceDecision(reason="approved", evidence=[document])
    outcome = derive_outcome(
        metadata={},
        language="en",
        country="US",
        question="What is the sponsoring contact for France?",
        answer_text="The France sponsoring contact is ...",
        evidence_decision=decision,
    )
    assert outcome.kind is OutcomeKind.INTERNATIONAL_DIRECTORY
    assert outcome.directory_target == "France"


def test_ordinary_same_market_directory_record_stays_answer_kind() -> None:
    document = _FakeDocument(
        {
            "directory_section": "office",
            "directory_fields": {"phone": "555-0100"},
            "record_country": "United States",
        }
    )
    decision = _FakeEvidenceDecision(reason="approved", evidence=[document])
    outcome = derive_outcome(
        metadata={},
        language="en",
        country="US",
        question="What is the office phone number?",
        answer_text="The office phone number is 555-0100.",
        evidence_decision=decision,
    )
    assert outcome.kind is OutcomeKind.ANSWER
    assert outcome.directory_target is None


def test_international_directory_does_not_override_an_explicit_failure_kind() -> None:
    document = _FakeDocument(
        {
            "directory_kind": "international_sponsoring",
            "record_country": "France",
        }
    )
    decision = _FakeEvidenceDecision(reason="insufficient_approved_evidence", evidence=[document])
    outcome = derive_outcome(
        metadata={"failure_layer": "evidence_gate"},
        language="en",
        country="US",
        question="What is the sponsoring contact for France?",
        answer_text="",
        evidence_decision=decision,
    )
    assert outcome.kind is OutcomeKind.EVIDENCE_MISSING
    # directory_target is still reported for diagnostics even though the
    # turn did not deliver an international-directory answer.
    assert outcome.directory_target == "France"


def test_fields_requested_reuses_directory_fields_helper() -> None:
    outcome = derive_outcome(
        metadata={},
        language="en",
        country="US",
        question="What is the phone number and email address?",
        answer_text="",
    )
    assert outcome.fields_requested == frozenset({"phone", "email", "address"})


def test_fields_requested_empty_when_nothing_confidently_understood() -> None:
    outcome = derive_outcome(
        metadata={},
        language="en",
        country="US",
        question="Tell me about the company.",
        answer_text="",
    )
    assert outcome.fields_requested == frozenset()


def test_fields_answered_and_unsupported_are_empty_pending_lane_2() -> None:
    outcome = derive_outcome(
        metadata={},
        language="en",
        country="US",
        question="What is the phone number?",
        answer_text="The phone number is 555-0100.",
    )
    assert outcome.fields_answered == frozenset()
    assert outcome.fields_unsupported == frozenset()


def test_to_metadata_is_json_serialisable_and_deterministic() -> None:
    outcome = derive_outcome(
        metadata={"failure_layer": "directory_clarification", "reference_candidates": ["France", "Italy"]},
        language="fr",
        country="FR",
        question="What is the telephone number and email address?",
        answer_text="",
    )
    payload = outcome.to_metadata()
    encoded = json.dumps(payload, sort_keys=True)
    assert json.loads(encoded) == payload
    # Deterministic: rebuilding from the same outcome yields byte-identical JSON.
    assert json.dumps(outcome.to_metadata(), sort_keys=True) == encoded
    assert payload["fields_requested"] == sorted(payload["fields_requested"])
    assert payload["kind"] == "clarification"
    assert payload["clarification_subject"] == "directory_reference"


def test_to_metadata_field_lists_are_sorted_lists_not_sets() -> None:
    outcome = ConversationOutcome(
        kind=OutcomeKind.ANSWER,
        language="en",
        country="US",
        fields_requested=frozenset({"website", "email", "address"}),
        fields_answered=frozenset(),
        fields_unsupported=frozenset(),
        directory_target=None,
        clarification_subject=None,
        failure_layer=None,
        retrieval_availability=None,
    )
    payload = outcome.to_metadata()
    assert payload["fields_requested"] == ["address", "email", "website"]
    assert isinstance(payload["fields_requested"], list)


def test_directory_clarification_with_reference_candidates_sets_reference_subject() -> None:
    outcome = derive_outcome(
        metadata={"failure_layer": "directory_clarification", "reference_candidates": ["France", "Italy"]},
        language="en",
        country="US",
        question="What about the other one?",
        answer_text="",
    )
    assert outcome.clarification_subject == "directory_reference"


def test_directory_clarification_without_reference_candidates_sets_field_subject() -> None:
    outcome = derive_outcome(
        metadata={"failure_layer": "directory_clarification"},
        language="en",
        country="US",
        question="Do you have contact information?",
        answer_text="",
    )
    assert outcome.clarification_subject == "directory_field"


def test_candidate_narrowing_fallback_sets_clarification_subject() -> None:
    outcome = derive_outcome(
        metadata={"failure_layer": "candidate_narrowing_fallback"},
        language="en",
        country="US",
        question="Tell me more.",
        answer_text="",
    )
    assert outcome.kind is OutcomeKind.CLARIFICATION
    assert outcome.clarification_subject == "candidate_narrowing"


def test_no_hardcoded_case_ids_in_this_module() -> None:
    # This is a meta-check on the test file itself: outcome derivation must
    # stay generic across markets/languages, never keyed to a specific
    # benchmark or support-ticket case id.
    ticket_prefix = "TRB"
    source = Path(__file__).read_text(encoding="utf-8")
    assert not re.search(rf"\b{ticket_prefix}-\d+\b", source)
    assert not re.search(r"\bcase[_-]?id\s*[:=]", source, re.IGNORECASE)
