"""Demo W1: "What are Kenya's business hours?" from a US session is refused.

Live (commit 92278e3): every Kenya directory turn was refused with
``evidence_decision.reason == "cross_market_local_evidence"`` and
``evidence_count == 0``, while "What is the delivery cost in Mali?" was
answered from ``sponsoring-014-mali``.

Reproduced offline below with rows shaped like real OpenSearch hits. The
evidence gate is NOT the cause: given the Kenya/East Africa record, the gate
approves it and drops the US rows. The record never reaches the gate.
``_directory_target_country_names`` targets ``{"Kenya"}``, and
``_directory_record_country_score`` compares the whole normalized
``record_country`` ("kenya east africa") against that set, so the record falls
through to the -4.0 wrong-country penalty. Its merged score goes negative and
``_finalize_eligible_rows`` drops it at ``SECTION_RETRIEVAL_MIN_SCORE``, even
when the evidence selector picked it. Only US rows remain; the orchestrator's
global-only reapproval is empty, hence ``cross_market_local_evidence``.

Mali ("Mali") and Netherlands Benelux (aliased to NL in
``global_directory_markets.json``) match their targets exactly and score +8.0.

Fix (applied by the orchestrator in ``app/retrieval/opensearch_sections.py``
after worker W1's diagnosis): the record-country score also accepts a
"/"-separated part of ``record_country`` equal to a target. On the unmodified
base these Kenya retrieval tests fail (fail-before); controls below still hold.
"""

from __future__ import annotations

import pytest

from app.evidence import approve_evidence
from app.governance.models import GovernanceAction, GovernanceDecision
from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.retrieval import opensearch_sections
from app.retrieval.models import RetrievalResult
from app.retrieval.opensearch_sections import (
    OpenSearchSectionProvider,
    _directory_record_country_score,
    _directory_target_country_names,
)
from app.retrieval.providers import RetrievalQueryPlan
from app.validation.models import ValidationResult
from config import settings
from utils.validators import ChatRequest

KENYA_ID = "sponsoring-012-kenya-east-africa"
KENYA_RECORD = "Kenya/East Africa"

CAUSE = (
    "_directory_record_country_score gives 'Kenya/East Africa' the -4.0 wrong-country "
    "penalty for target {'Kenya'}; the row is dropped at the score floor before the gate"
)


def _policy_hit(section_id: str, title: str, score: float, country: str = "US") -> dict:
    return {
        "_id": f"{country}:{section_id}",
        "_score": score,
        "_source": {
            "id": f"{country}:{section_id}",
            "section_id": section_id,
            "section_title": title,
            "content": f"{title}. Customer care business hours, phone number, address and minimum order.",
            "search_text": f"{title} customer care business hours phone address minimum order",
            "country": country,
            "language": "en",
            "status": "active",
            "access_scope": "country",
            "document_type": "policy",
        },
    }


def _directory_hit(record_id: str, record_country: str, score: float = 8.0) -> dict:
    return {
        "_id": record_id,
        "_score": score,
        "_source": {
            "id": record_id,
            "section_id": record_id,
            "section_title": f"Forever {record_country}",
            "source_file": "International Sponsoring Directory",
            "content": (
                f"Welcome to Forever {record_country}!\n"
                "Business Hours Monday - Friday 8:00 - 17:00\n"
                "Telephone Office +000 000 000\n"
                "Address 1 Example Road\n"
                "Minimum order size 50 USD"
            ),
            "search_text": f"Forever {record_country} business hours telephone address minimum order",
            "country": "GLOBAL",
            "language": "en",
            "status": "active",
            "access_scope": "global",
            "document_type": "office_directory",
            "metadata": {
                "directory_kind": "international_sponsoring",
                "directory_section": "sponsoring",
                "record_country": record_country,
            },
        },
    }


class _Client:
    """Locale searches return US policy rows; global searches return the directory rows."""

    def __init__(self, global_hits: list[dict], local_hits: list[dict] | None = None) -> None:
        self.global_hits = global_hits
        self.local_hits = local_hits if local_hits is not None else [
            _policy_hit("6.01", "Customer Care", 12.0),
            _policy_hit("3.02", "Ordering", 9.0),
        ]

    def search(self, index: str, body: dict) -> dict:
        del index
        is_global = "'access_scope': 'global'" in repr(body)
        return {"hits": {"hits": list(self.global_hits if is_global else self.local_hits)}}


class _Governance:
    def evaluate(self, **_: object) -> GovernanceDecision:
        return GovernanceDecision(allowed=True, action=GovernanceAction.ALLOW, provider="test")


class _Validator:
    def validate(self, *_: object, **__: object) -> ValidationResult:
        return ValidationResult()


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    """No embeddings, planner, selector, translation or AWS client may run."""
    monkeypatch.setattr(opensearch_sections, "embed_text", lambda *_a, **_k: [0.0])
    monkeypatch.setattr(
        opensearch_sections,
        "get_aws_clients",
        lambda: (_ for _ in ()).throw(AssertionError("AWS must not be called")),
    )
    monkeypatch.setattr(settings, "OPENSEARCH_EVIDENCE_SELECTOR_ENABLED", False)
    monkeypatch.setattr(settings, "RETRIEVAL_PARENT_DIVERSITY_ENABLED", False)
    monkeypatch.setattr(settings, "ADMIN_INGESTION_GENERATION_POINTER_ENABLED", False)
    monkeypatch.setattr(chat_orchestrator, "append_session_turn", lambda *_: None)


def _retrieve(monkeypatch, question: str, client: _Client, country: str = "US") -> RetrievalResult:
    provider = OpenSearchSectionProvider()
    monkeypatch.setattr(opensearch_sections, "_client", lambda: client)
    monkeypatch.setattr(
        provider, "_build_search_plan", lambda *_: RetrievalQueryPlan([question], include_global_documents=True)
    )
    monkeypatch.setattr(provider, "_global_search_query", lambda message, *_: message)
    return provider.retrieve(question, country, "en", "fbo", "cid")


def _gate(question: str, result: RetrievalResult, country: str = "US", history: str = ""):
    orchestrator = AIOrchestrator(validator=_Validator(), governance=_Governance())
    orchestrator._office_contact_addendum = lambda *_: ""
    body = ChatRequest(message=question, sessionId="w1", country=country, language="en")
    return orchestrator._route_or_approve_evidence(question, result, question, body, "cid", history=history)


KENYA_QUESTIONS = [
    "What are Kenya's business hours?",
    # Follow-ups reach retrieval as their history-resolved query.
    "What are Kenya's business hours? What is the phone number?",
    "What are Kenya's business hours? And the address?",
    "What is Kenya's minimum order size and how do I get help if I have a problem?",
]


# --- confirmed cause (fail-before) ----------------------------------------


def test_kenya_east_africa_record_scores_as_the_named_market() -> None:
    question = "What are Kenya's business hours?"
    targets = _directory_target_country_names(question, "US")
    row = {"document_type": "office_directory", "metadata": {"record_country": KENYA_RECORD}}

    assert targets == {"Kenya"}
    assert _directory_record_country_score(question, row, targets) == 8.0


@pytest.mark.parametrize("question", KENYA_QUESTIONS)
def test_kenya_directory_question_from_us_session_is_answered_from_the_kenya_record(monkeypatch, question) -> None:
    result = _retrieve(monkeypatch, question, _Client([_directory_hit(KENYA_ID, KENYA_RECORD)]))
    response, approved, decision = _gate(question, result)

    assert decision is not None and decision.approved is True, decision and decision.to_metadata()
    assert response is None
    assert [document.id for document in approved.documents] == [KENYA_ID]


def test_kenya_record_now_survives_retrieval_instead_of_being_filtered(monkeypatch) -> None:
    """The live refusal came from retrieval dropping the record; it must now reach the documents."""
    question = "What are Kenya's business hours?"
    result = _retrieve(monkeypatch, question, _Client([_directory_hit(KENYA_ID, KENYA_RECORD)]))

    assert KENYA_ID in [document.id for document in result.documents]


def test_a_record_segment_never_matches_a_different_country() -> None:
    """Only whole "/"-separated parts count: "Guinea" is not "Equatorial Guinea"."""
    row = {"document_type": "office_directory", "metadata": {"record_country": "Equatorial Guinea"}}
    east_africa = {"document_type": "office_directory", "metadata": {"record_country": KENYA_RECORD}}

    assert _directory_record_country_score("What is Guinea's phone number?", row, {"Guinea"}) == -4.0
    assert _directory_record_country_score("Uganda office hours?", east_africa, {"Uganda"}) == -4.0


# --- the gate is not the cause --------------------------------------------


@pytest.mark.parametrize("question", KENYA_QUESTIONS)
def test_gate_answers_kenya_from_the_global_record_when_retrieval_returns_it(question) -> None:
    provider = OpenSearchSectionProvider()
    kenya = provider._document_from_row(opensearch_sections._hit_to_row(_directory_hit(KENYA_ID, KENYA_RECORD)), 9.0)
    us = provider._document_from_row(opensearch_sections._hit_to_row(_policy_hit("6.01", "Customer Care", 1.0)), 2.1)
    result = RetrievalResult(documents=[us, kenya], citations=[], confidence=0.9)

    response, approved, decision = _gate(question, result)

    assert kenya.metadata["access_scope"] == "global"
    assert decision is not None and decision.approved is True
    assert response is None
    assert [document.id for document in approved.documents] == [KENYA_ID]


# --- controls ---------------------------------------------------------------


def test_mali_global_only_market_is_unchanged(monkeypatch) -> None:
    question = "What is the delivery cost in Mali?"
    result = _retrieve(monkeypatch, question, _Client([_directory_hit("sponsoring-014-mali", "Mali")]))
    response, approved, decision = _gate(question, result)

    assert decision is not None and decision.approved is True
    assert response is None
    assert [document.id for document in approved.documents] == ["sponsoring-014-mali"]


@pytest.mark.parametrize("session", ["US", "BE"])
def test_netherlands_benelux_directory_question_from_another_market_is_answered(monkeypatch, session) -> None:
    question = "What are the Netherlands business hours?"
    record_id = "sponsoring-080-netherlands-benelux"
    client = _Client(
        [_directory_hit(record_id, "Netherlands Benelux")],
        [_policy_hit("6.01", "Customer Care", 12.0, country=session)],
    )
    result = _retrieve(monkeypatch, question, client, country=session)
    response, approved, decision = _gate(question, result, country=session)

    assert decision is not None and decision.approved is True
    assert response is None
    assert [document.id for document in approved.documents] == [record_id]


@pytest.mark.parametrize(
    "question",
    [
        "What is Kenya's company policy on returns?",
        "What is Italy's company policy on returns?",
        "What is the Italian company policy on returns?",
    ],
)
def test_foreign_company_policy_request_is_still_refused(monkeypatch, question) -> None:
    client = _Client([_directory_hit(KENYA_ID, KENYA_RECORD), _directory_hit("sponsoring-italy", "Italy")])
    result = _retrieve(monkeypatch, question, client)
    response, approved, decision = _gate(question, result)

    assert decision is not None and decision.reason == "cross_market_policy_request"
    assert approved.documents == []
    assert response is not None and response.metadata["failure_layer"] == "evidence_gate"


def test_local_us_rows_never_answer_a_kenya_question(monkeypatch) -> None:
    question = "What are Kenya's business hours?"
    result = _retrieve(monkeypatch, question, _Client([]))
    rescued = RetrievalResult(documents=result.documents, citations=result.citations, confidence=0.9)
    response, approved, decision = _gate(question, rescued)

    assert decision is not None and decision.approved is False
    assert decision.reason == "cross_market_local_evidence"
    assert approved.documents == []
    assert response is not None


@pytest.mark.parametrize(
    ("question", "wrong_id", "wrong_country"),
    [
        ("What are Kenya's business hours?", "sponsoring-025-uganda", "Uganda"),
        ("What are Kenya's business hours?", "sponsoring-e-africa", "East Africa"),
        ("What are Uganda's business hours?", KENYA_ID, KENYA_RECORD),
        ("What is the delivery cost in Mali?", KENYA_ID, KENYA_RECORD),
    ],
)
def test_directory_record_for_a_different_country_is_never_used(monkeypatch, question, wrong_id, wrong_country) -> None:
    result = _retrieve(monkeypatch, question, _Client([_directory_hit(wrong_id, wrong_country)]))

    assert wrong_id not in [document.id for document in result.documents]
    rescued = RetrievalResult(documents=result.documents, citations=result.citations, confidence=0.9)
    _, approved, _ = _gate(question, rescued)
    assert wrong_id not in [document.id for document in approved.documents]


@pytest.mark.parametrize("question", ["What is the delivery cost in South Sudan?", "What is the minimum order in Ethiopia?"])
def test_shared_office_rule_still_reaches_kenya_east_africa(monkeypatch, question) -> None:
    """Unchanged baseline: the serving record leads the approved evidence.

    South Sudan and Ethiopia are not markets, so ``find_market_mentions`` does
    not see them and the cross-market narrowing does not run; the session's
    own rows stay in context behind the directory record (pre-existing, not
    changed by W1).
    """
    result = _retrieve(monkeypatch, question, _Client([_directory_hit(KENYA_ID, KENYA_RECORD)]))
    response, approved, decision = _gate(question, result)

    assert _directory_target_country_names(question, "US") == {KENYA_RECORD}
    assert decision is not None and decision.approved is True
    assert response is None
    assert [document.id for document in approved.documents][0] == KENYA_ID


def test_gate_decision_for_a_lone_kenya_record_is_approved() -> None:
    """approve_evidence does not reject a lone global directory record for an enabled market."""
    provider = OpenSearchSectionProvider()
    kenya = provider._document_from_row(opensearch_sections._hit_to_row(_directory_hit(KENYA_ID, KENYA_RECORD)), 9.0)
    decision = approve_evidence(
        "What are Kenya's business hours?", RetrievalResult(documents=[kenya], citations=[], confidence=0.9), "US", "en"
    )

    assert decision.approved is True
    assert [document.id for document in decision.evidence] == [KENYA_ID]
