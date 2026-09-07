from dataclasses import replace

import pytest

from app.retrieval.evidence_decision import validate_decision
from app.retrieval.source_binding import EvidenceSource


SOURCE = EvidenceSource("policy", "v1", "rule", "CA", "A renewal is required every month.")


def answer():
    return {"decision": "ANSWER_FACT", "draft_answer": "Renew each month.", "missing_facts": [],
            "confidence": 0.9, "support": [{"source_id": SOURCE.binding_id, "quote": SOURCE.content}]}


def test_citations_derive_from_quotes_and_preserve_multiple_quotes():
    payload = answer()
    payload["support"].append({"source_id": SOURCE.binding_id, "quote": "every month"})
    decision = validate_decision(payload, [SOURCE])
    assert decision.source_ids == (SOURCE.binding_id,)
    assert len(decision.support) == 2
    assert len(payload["support"]) == 2


@pytest.mark.parametrize("change", [
    {"selected_source_ids": []}, {"selected_ranks": [1]}, {"answer_supported": True},
    {"decision": "bad"}, {"decision": []}, {"draft_answer": " "}, {"draft_answer": None},
    {"missing_facts": ["renewal rule"]}, {"missing_facts": None}, {"missing_facts": [""]},
    {"confidence": True}, {"confidence": -1}, {"confidence": 2}, {"confidence": float("nan")},
    {"confidence": float("inf")}, {"confidence": "0.9"}, {"support": []}, {"support": None},
])
def test_inconsistent_answer_rejected(change):
    with pytest.raises(ValueError):
        validate_decision({**answer(), **change}, [SOURCE])


def test_missing_evidence_is_never_a_supported_no():
    payload = {**answer(), "decision": "ANSWER_NO", "missing_facts": ["automatic termination rule"]}
    with pytest.raises(ValueError, match="missing required"):
        validate_decision(payload, [SOURCE])
    payload.update(decision="INSUFFICIENT_EVIDENCE", draft_answer="", support=[])
    assert validate_decision(payload, [SOURCE]).source_ids == ()


@pytest.mark.parametrize("change", [{"draft_answer": "No."}, {"support": answer()["support"]}, {"missing_facts": []}])
def test_inconsistent_abstention_rejected(change):
    payload = {**answer(), "decision": "INSUFFICIENT_EVIDENCE", "draft_answer": "", "support": [],
               "missing_facts": ["rule"], **change}
    with pytest.raises(ValueError):
        validate_decision(payload, [SOURCE])


def test_wrong_source_is_rejected_before_any_ordering():
    other = replace(SOURCE, section_id="other", content="A different rule.")
    payload = answer()
    payload["support"][0]["source_id"] = other.binding_id
    with pytest.raises(ValueError, match="does not belong"):
        validate_decision(payload, [SOURCE, other])
