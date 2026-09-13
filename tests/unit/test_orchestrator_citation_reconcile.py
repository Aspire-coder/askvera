"""Orchestrator wiring: citations for the answer that survives repair and output cleanup (PROPOSED).

The wiring is not applied in this worktree; the orchestrator belongs to another
worker. It is delivered as
docs/agent-handoffs/claude-to-codex/2026-09-11_1625_ovn-w4-orchestrator-wiring.patch.txt.

Until that patch is applied, every test marked `_needs_wiring` is a strict xfail:
it reproduces the defect and is NOT coverage. Once the patch is applied the
marker's condition is false, the tests run normally, and an unexpected failure
or pass is reported.

Only the external PII detection boundary is replaced; the builder, output
validator, numeric repair and output cleanup are real.
"""

import inspect

import pytest

from app.governance.models import GovernanceAction, GovernanceDecision
from app.models.responses import ModelResponse
from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.response.models import ChatResponse
from app.retrieval.models import RetrievedDocument, RetrievalResult
from utils.validators import ChatRequest

_WIRED = "reconcile_citations" in inspect.getsource(chat_orchestrator)
_needs_wiring = pytest.mark.xfail(
    not _WIRED,
    strict=True,
    reason="KNOWN GAP (not coverage): needs the proposed orchestrator wiring patch "
    "2026-09-11_1625_ovn-w4-orchestrator-wiring.patch.txt",
)


@pytest.fixture(autouse=True)
def _offline_pii_detection(monkeypatch):
    from services import pii

    monkeypatch.setattr(pii, "_detect_pii_entities", lambda text, _: [])


class _AllowGovernance:
    def evaluate(self, *, text: str, **_: object) -> GovernanceDecision:
        return GovernanceDecision(allowed=True, action=GovernanceAction.ALLOW, provider="test")


def _doc(doc_id, country, section, content, score, parent="", directory=False):
    metadata = {"section_id": section, "parent_section_id": parent}
    if directory:
        metadata.update({"directory_section": "sponsoring", "directory_kind": "international_sponsoring"})
    return RetrievedDocument(id=doc_id, title=f"{country} {section}", content=content, source=f"s3://kb/{doc_id}",
                             country=country, language="en", score=score, metadata=metadata)


_DIRECTORY = (
    "Welcome to Forever Denmark!\n+45 70 20 30 40\nDelivery Cost: under 2CC - €18 ex VAT per order.\n"
    "Business Hours Office 09.00 am - 16.00 pm (Mon - Fri)\nTelephone Office +45 70 20 30 40\nEmail service@example.dk"
)
_CONTACTS = "\nPhone: +45 70 20 30 40\nEmail: service@example.dk"
_TRIP_SENTENCE = "Incentive trips must be taken within 24 months of qualifying."
_INVENTED = (
    "\nThe booking deposit is 450 EUR, the travel insurance premium is 35 EUR, the airport transfer costs 65 EUR, "
    "the hotel city tax is 12 EUR per night, the excursion package costs 180 EUR, the luggage allowance is 23 kg, "
    "and the guest supplement is 390 EUR for each accompanying adult traveller sharing the room."
)


def _documents(policy_country="DK"):
    return [
        _doc(f"{policy_country}:6.02-c", policy_country, "6.02-c",
             "Section 6.02: c) Incentive trips must be taken within 24 months of qualifying.", 0.9, parent="6.02"),
        _doc("GLOBAL:sponsoring-dk", "GLOBAL", "sponsoring-dk", _DIRECTORY, 0.8, directory=True),
    ]


def _sections(citations):
    return [(citation.get("country"), citation.get("section")) for citation in citations]


def _deliver(model_text, documents, country="DK"):
    """Run the generated-answer path from citation building through validation and repair."""
    orchestrator = AIOrchestrator(governance=_AllowGovernance())
    retrieval_result = RetrievalResult(documents, [], 0.9)
    model_response = ModelResponse(text=model_text, citations=[], confidence=0.9, provider="claude", model_name="m")
    body = ChatRequest(message="How long do I have to take my incentive trip?", sessionId="session-1",
                       country=country, language="en")
    built = orchestrator.response_builder.build(
        model_response=model_response, retrieval_result=retrieval_result, correlation_id="test",
        session_metadata={"country": country, "language": "en"},
    )
    secured = orchestrator._secure_and_complete_response(
        built, retrieval_result, "en", "test", user_question=body.message, country=country
    )
    delivered = orchestrator._validate_response(
        secured, body, "test", model_response=model_response, retrieval_result=retrieval_result
    )
    return built, delivered


@_needs_wiring
def test_policy_citation_is_dropped_when_repair_deletes_the_claim_it_supported() -> None:
    model_text = "Incentive trips must be taken within 24 months of qualifying, with a travel deposit of 450 EUR." + _CONTACTS
    built, delivered = _deliver(model_text, _documents())

    assert delivered.metadata.get("numeric_claim_repair") is True
    assert "24 months" not in delivered.answer
    assert ("DK", "6.02") in _sections(built.citations)
    assert _sections(delivered.citations) == [("GLOBAL", "sponsoring-dk")]


@_needs_wiring
def test_repaired_answer_is_cited_to_the_support_it_still_has() -> None:
    built, delivered = _deliver(_TRIP_SENTENCE + _INVENTED + _CONTACTS, _documents())

    assert delivered.metadata.get("numeric_claim_repair") is True
    assert built.citations == []
    assert _sections(delivered.citations) == [("GLOBAL", "sponsoring-dk"), ("DK", "6.02")]


@_needs_wiring
def test_another_markets_policy_is_not_cited_after_repair() -> None:
    _built, delivered = _deliver(_TRIP_SENTENCE + _INVENTED + _CONTACTS, _documents(policy_country="SE"))

    assert delivered.metadata.get("numeric_claim_repair") is True
    assert _sections(delivered.citations) == [("GLOBAL", "sponsoring-dk")]


def test_answer_that_needs_no_repair_keeps_its_built_citations() -> None:
    built, delivered = _deliver(_TRIP_SENTENCE + _CONTACTS, _documents())

    assert not delivered.metadata.get("numeric_claim_repair")
    assert _sections(built.citations) == [("GLOBAL", "sponsoring-dk"), ("DK", "6.02")]
    assert delivered.citations == built.citations


@_needs_wiring
def test_refusal_that_replaces_an_emptied_answer_carries_no_citation() -> None:
    documents = _documents()
    orchestrator = AIOrchestrator(governance=_AllowGovernance())
    response = ChatResponse(answer="[NAME]", citations=[documents[0].to_source()], suggestions=[], cards=[],
                            confidence=0.9, metadata={}, correlation_id="test")
    cleaned = orchestrator._secure_and_complete_response(
        response, RetrievalResult(documents, [], 0.9), "en", "test", user_question="How long?", country="DK"
    )

    assert cleaned.metadata.get("empty_after_output_cleanup") is True
    assert cleaned.citations == []


# The following run unconditionally. They pass without the wiring (citations are
# copied through repair) and with the v2 wiring; they fail with the v1 wiring
# (feb63e8c), which reconciled fallback copy and let a reconcile error escape.
_FALLBACK_SHAPES = {
    "fallback with failure_layer": {"failure_layer": "evidence_gate"},
    "narrowing: failure_layer without fallback": {
        "failure_layer": "candidate_narrowing_fallback",
        "response_source": "candidate_narrowing_fallback",
        "fallback": False,
    },
    "controlled copy source without failure_layer": {"fallback": False, "response_source": "template"},
}


@pytest.mark.parametrize("shape", sorted(_FALLBACK_SHAPES))
def test_repaired_fallback_or_controlled_copy_never_gains_a_citation(shape) -> None:
    orchestrator = AIOrchestrator(governance=_AllowGovernance())
    body = ChatRequest(message="How long do I have to take my incentive trip?", sessionId="session-1",
                       country="DK", language="en")
    refusal = orchestrator._insufficient_evidence_message("en", body.message)
    documents = [
        _doc("DK:1.01", "DK", "1.01", "Section 1.01: The approved documents contain the information needed; sorry is "
             "not enough. Incentive trips must be taken within 24 months of qualifying.", 0.9),
        _documents()[1],
    ]
    response = orchestrator.response_builder.fallback(
        refusal + "\n\nYou can contact Forever Denmark on +45 99 88 77 66 (fee 450 EUR).", "test",
        metadata=_FALLBACK_SHAPES[shape],
    )
    delivered = orchestrator._validate_response(response, body, "test", retrieval_result=RetrievalResult(documents, [], 0.9))

    assert delivered.metadata.get("numeric_claim_repair") is True
    assert delivered.citations == []


def test_a_citation_choice_error_keeps_the_pre_repair_citations(monkeypatch) -> None:
    orchestrator = AIOrchestrator(governance=_AllowGovernance())

    def failing_reconcile(**_: object) -> list:
        raise AttributeError("malformed evidence")

    monkeypatch.setattr(orchestrator.response_builder, "reconcile_citations", failing_reconcile, raising=False)
    documents = _documents()
    retrieval_result = RetrievalResult(documents, [], 0.9)
    model_text = "Incentive trips must be taken within 24 months of qualifying, with a travel deposit of 450 EUR." + _CONTACTS
    model_response = ModelResponse(text=model_text, citations=[], confidence=0.9, provider="claude", model_name="m")
    body = ChatRequest(message="How long?", sessionId="session-1", country="DK", language="en")
    built = orchestrator.response_builder.build(
        model_response=model_response, retrieval_result=retrieval_result, correlation_id="test",
        session_metadata={"country": "DK", "language": "en"},
    )
    delivered = orchestrator._validate_response(
        built, body, "test", model_response=model_response, retrieval_result=retrieval_result
    )

    assert delivered.metadata.get("numeric_claim_repair") is True
    assert delivered.citations == built.citations


def test_malformed_evidence_does_not_fail_a_repaired_answer() -> None:
    policy = _documents()[0]
    malformed = RetrievedDocument(id="X", title="", content=None, source="s3://x", country="DK", language="en",
                                  score=0.1, metadata=None)
    answer = "Incentive trips must be taken within 24 months of qualifying. The deposit is 450 EUR."
    response = ChatResponse(answer=answer, citations=[policy.to_source()], suggestions=[], cards=[], confidence=0.9,
                            metadata={}, correlation_id="test")
    orchestrator = AIOrchestrator(governance=_AllowGovernance())
    body = ChatRequest(message="How long?", sessionId="session-1", country="DK", language="en")
    delivered = orchestrator._validate_response(
        response, body, "test",
        model_response=ModelResponse(text=answer, citations=[], confidence=0.9, provider="claude", model_name="m"),
        retrieval_result=RetrievalResult([policy, malformed], [], 0.9),
    )

    assert delivered.metadata.get("numeric_claim_repair") is True
    assert delivered.citations == [policy.to_source()]
