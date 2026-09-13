"""A company-policy question that names a foreign market only as a sponsoring destination is answered.

"What is the company policy on sponsoring someone in Italy?" from an Austrian
session used to be refused whole as a cross-market policy request, because the
gate saw the words "company policy" and the name "Italy". Italy is where the
person being sponsored lives, not whose policy is asked for. Sponsoring facts
for another country come from the GLOBAL International Sponsoring Directory,
and any local-policy part may only come from the session's own policy. These
tests pin that split and every nearby wording that must keep being refused.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import evidence
from app.evidence import approve_evidence
from app.governance.models import GovernanceAction, GovernanceDecision
from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.retrieval.models import RetrievedDocument, RetrievalResult
from app.validation.models import ValidationResult
from utils.validators import ChatRequest

PACK_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "held_out_source_linked_pack.json"
DIRECTORY_SLUG = {"IT": "italy", "CA": "canada", "GH": "ghana"}


def _document(doc_id: str, country: str, language: str, scope: str, document_type: str, score: float) -> RetrievedDocument:
    return RetrievedDocument(
        id=doc_id,
        title=doc_id,
        content="Sponsoring requirements, minimum first order, promoter commission and order discrepancies.",
        source=f"s3://approved/{doc_id}",
        country=country,
        language=language,
        score=score,
        metadata={"access_scope": scope, "document_type": document_type, "status": "active"},
    )


def _retrieval(session: str, language: str, destination: str) -> RetrievalResult:
    """The session's policy, the destination's GLOBAL directory record, and a foreign policy row.

    Retrieval's country filter never returns the foreign policy row; it is here
    so every test also proves the gate would drop it.
    """
    documents = [
        _document(f"{destination}:4.01", destination, "en", "country", "policy", 0.95),
        _document(f"{session}:4.01", session, language, "country", "policy", 0.9),
        _document(
            f"GLOBAL:sponsoring-{DIRECTORY_SLUG[destination]}",
            "GLOBAL",
            "en",
            "global",
            "international_sponsoring_directory",
            0.8,
        ),
    ]
    return RetrievalResult(documents=documents, citations=[], confidence=0.9, metadata={})


def _ids(decision) -> list[str]:
    return [document.id for document in decision.evidence]


MIXED_QUESTIONS = [
    "What is the company policy on sponsoring someone in Italy?",
    "Can I sponsor someone in Italy, and what does the company policy say?",
    "Can I sponsor someone in Italy and what does the company policy say?",
    "What is the company policy for sponsoring someone who lives in Italy?",
    "Can I sponsor someone in Italy, and what does the Austrian company policy say?",
]


@pytest.mark.parametrize("question", MIXED_QUESTIONS)
def test_mixed_sponsoring_question_is_approved_with_global_destination_and_own_policy(question) -> None:
    decision = approve_evidence(question, _retrieval("AT", "en", "IT"), "AT", "en")

    assert decision.approved is True
    assert decision.reason == "approved"
    assert _ids(decision) == ["AT:4.01", "GLOBAL:sponsoring-italy"]


@pytest.mark.parametrize(
    "session, question, destination",
    [
        # The policy wording itself claims the foreign market's policy.
        ("AT", "What is Italy's company policy on promoter commission?", "IT"),
        ("AT", "What is the Italian company policy on promoter commission?", "IT"),
        ("AT", "What does the Italian company policy say about sponsoring?", "IT"),
        ("AT", "What is the company policy of Italy on sponsoring?", "IT"),
        ("AT", "What is the company policy in Italy on sponsoring someone?", "IT"),
        ("AT", "Under Forever Italy's company policy, can I sponsor someone?", "IT"),
        ("AT", "Can I sponsor someone under Italy's company policy?", "IT"),
        ("AT", "What is Italy's company policy on sponsoring someone in Italy?", "IT"),
        ("AT", "What is the Italian company policy on sponsoring someone in Italy?", "IT"),
        ("AT", "Can I sponsor someone in Italy and what is Italy's company policy?", "IT"),
        ("AT", "What is the company policy on sponsoring someone in Italy under Italy's company policy?", "IT"),
        # The foreign market belongs to a non-sponsoring part of the question.
        ("AT", "What is the company policy on promoter commission in Italy?", "IT"),
        ("AT", "What is the company policy on sponsoring and promoter commission in Italy?", "IT"),
        # Case-08 shape.
        ("GB", "What is the Canadian company policy on order discrepancies?", "CA"),
    ],
)
def test_wording_that_claims_or_attaches_to_foreign_policy_is_still_refused(session, question, destination) -> None:
    decision = approve_evidence(question, _retrieval(session, "en", destination), session, "en")

    assert decision.approved is False
    assert decision.reason == "cross_market_policy_request"
    assert decision.evidence == []


@pytest.mark.parametrize(
    "session, question, destination, expected_ids",
    [
        # Case-12 shape: global directory fact for a named foreign market.
        (
            "GB",
            "I'm an FBO living outside Ghana. How much do I need to earn before Forever Ghana pays my bonus, "
            "and who covers the bank transfer charges?",
            "GH",
            ["GB:4.01", "GLOBAL:sponsoring-ghana"],
        ),
        ("GB", "What is the minimum first order for joining Forever Italy?", "IT", ["GB:4.01", "GLOBAL:sponsoring-italy"]),
        ("AT", "Can I sponsor an Italian person?", "IT", ["AT:4.01", "GLOBAL:sponsoring-italy"]),
        ("AT", "Can I sponsor someone in Italy?", "IT", ["AT:4.01", "GLOBAL:sponsoring-italy"]),
        ("AT", "What are the Italian sponsoring rules?", "IT", ["AT:4.01", "GLOBAL:sponsoring-italy"]),
        # Own-market policy question: the company-policy request still excludes global rows.
        ("AT", "What is the company policy on promoter commission?", "IT", ["AT:4.01"]),
        ("AT", "What is the company policy on sponsoring?", "IT", ["AT:4.01"]),
    ],
)
def test_controls_keep_their_current_approved_evidence(session, question, destination, expected_ids) -> None:
    decision = approve_evidence(question, _retrieval(session, "en", destination), session, "en")

    assert decision.approved is True
    assert _ids(decision) == expected_ids


@pytest.mark.parametrize(
    "session, question, expected",
    [
        *[("AT", question, True) for question in MIXED_QUESTIONS],
        # Only a foreign destination turns a company-policy request into a mixed one.
        ("AT", "What is the company policy on sponsoring someone in Austria?", False),
        # No company-policy request at all: nothing to split.
        ("AT", "Can I sponsor someone in Italy?", False),
        # The foreign market claims the policy, or sits outside the sponsoring clause.
        ("AT", "What is Italy's company policy on sponsoring someone in Italy?", False),
        ("AT", "Can I sponsor someone under Italy's company policy?", False),
        ("AT", "What is the company policy on sponsoring and promoter commission in Italy?", False),
        ("GB", "What is the Canadian company policy on order discrepancies?", False),
    ],
)
def test_mixed_sponsoring_policy_request_classification(session, question, expected) -> None:
    assert evidence.is_mixed_sponsoring_policy_request(question, session) is expected


@pytest.mark.parametrize(
    "case_number, destination, expected_reason",
    [("08", "CA", "cross_market_policy_request"), ("12", "GH", "approved"),
     ("22", "IT", "cross_market_policy_request"), ("23", "IT", "approved")],
)
def test_held_out_scope_cases_keep_their_gate_decision(case_number, destination, expected_reason) -> None:
    """Regression only: the frozen pack's wording, read, never tuned to."""
    pack = json.loads(PACK_PATH.read_text(encoding="utf-8"))
    case = next(item for item in pack["cases"] if item["id"].startswith(f"ho-slp-{case_number}-"))
    decision = approve_evidence(
        case["question"], _retrieval(case["country"], case["language"], destination), case["country"], case["language"]
    )

    assert decision.reason == expected_reason
    assert f"{destination}:4.01" not in _ids(decision)


@pytest.mark.parametrize(
    "question",
    [
        "What is the company policy on sponsoring someone in Italy — what is Italy's promoter commission?",
        "What is the company policy on sponsoring someone in Italy – what is Italy's promoter commission?",
        "What is the company policy on sponsoring someone in Italy - what is Italy's promoter commission?",
        "What is the company policy on sponsoring someone in Italy\nwhat is Italy's promoter commission?",
    ],
)
def test_clause_break_on_dash_and_newline_is_still_refused(question) -> None:
    """An em dash, en dash, spaced hyphen or newline ends the sponsoring clause too.

    Without a break there, "Italy's promoter commission" fell inside the same
    clause as "sponsoring someone in Italy" and the whole question was wrongly
    approved from GLOBAL only, instead of being refused as cross-market.
    """
    decision = approve_evidence(question, _retrieval("AT", "en", "IT"), "AT", "en")

    assert decision.approved is False
    assert decision.reason == "cross_market_policy_request"
    assert decision.evidence == []


@pytest.mark.parametrize(
    "question",
    [
        "What is the company policy on sponsoring someone in Italy?",
        "What is the company policy on co-sponsoring someone in Italy?",
    ],
)
def test_unspaced_hyphen_inside_a_word_does_not_break_the_clause(question) -> None:
    """A hyphenated word like "co-sponsoring" keeps Italy inside the sponsoring clause."""
    decision = approve_evidence(question, _retrieval("AT", "en", "IT"), "AT", "en")

    assert decision.approved is True
    assert decision.reason == "approved"
    assert _ids(decision) == ["AT:4.01", "GLOBAL:sponsoring-italy"]


def test_bare_foreign_policy_wording_never_carries_foreign_policy_rows() -> None:
    """Pre-existing trigger gap, unchanged here: no company/local/national word, so no refusal.

    The foreign policy row is still never approved evidence.
    """
    decision = approve_evidence("What is the Italian policy on sponsoring?", _retrieval("AT", "en", "IT"), "AT", "en")

    assert "IT:4.01" not in _ids(decision)


class _Governance:
    def evaluate(self, **_: object) -> GovernanceDecision:
        return GovernanceDecision(allowed=True, action=GovernanceAction.ALLOW, provider="test")


class _Validator:
    def validate(self, *_: object, **__: object) -> ValidationResult:
        return ValidationResult()


@pytest.mark.parametrize("question", MIXED_QUESTIONS[:2])
def test_orchestrator_answers_mixed_question_from_the_global_directory(monkeypatch, question) -> None:
    """End to end through the offline gate: no refusal and no foreign policy row in model context.

    The orchestrator's cross-market guard (not edited here) still narrows the
    context to global evidence because the message names Italy, so the AT
    policy row is removed at that layer. See the handoff for the proposed hunk.
    """
    monkeypatch.setattr(chat_orchestrator, "append_session_turn", lambda *_: None)
    orchestrator = AIOrchestrator(validator=_Validator(), governance=_Governance())
    body = ChatRequest(message=question, sessionId="t2", country="AT", language="en")

    response, approved, decision = orchestrator._route_or_approve_evidence(
        question, _retrieval("AT", "en", "IT"), question, body, "cid"
    )

    assert decision is not None and decision.approved is True
    assert response is None
    assert [document.id for document in approved.documents] == ["GLOBAL:sponsoring-italy"]
