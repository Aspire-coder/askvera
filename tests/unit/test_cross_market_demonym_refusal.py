"""A company-policy request that names another market by its adjective is refused.

"What is the Italian company policy on promoter commission?" from an Austrian
session used to be approved on Austria's own policy row, because only market
names were recognised. Retrieval never returns another market's local policy,
so this was never a disclosure; but the answer would present Austria's rule as
the answer to a question about Italy. These tests pin the refusal and, just as
importantly, every nearby wording that must keep answering.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.evidence import approve_evidence
from app.governance.models import GovernanceAction, GovernanceDecision
from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import AIOrchestrator, CROSS_MARKET_POLICY_SCOPE_RESPONSE
from app.retrieval.models import RetrievedDocument, RetrievalResult
from app.validation.models import ValidationResult
from services import market_config
from utils.validators import ChatRequest

PACK_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "held_out_source_linked_pack.json"


def _document(doc_id: str, country: str, language: str, scope: str, document_type: str) -> RetrievedDocument:
    return RetrievedDocument(
        id=doc_id,
        title=doc_id,
        content="Promoter commission and sponsoring requirements.",
        source=f"s3://approved/{doc_id}",
        country=country,
        language=language,
        score=0.9 if scope == "country" else 0.8,
        metadata={"access_scope": scope, "document_type": document_type, "status": "active"},
    )


def _retrieval(session: str, language: str, *extra: RetrievedDocument) -> RetrievalResult:
    documents = [
        _document(f"{session}:4.01", session, language, "country", "policy"),
        _document("GLOBAL:sponsoring-italy", "GLOBAL", "en", "global", "international_sponsoring_directory"),
        *extra,
    ]
    return RetrievalResult(documents=documents, citations=[], confidence=0.9, metadata={})


def _reason(question: str, session: str, language: str = "en") -> str:
    return approve_evidence(question, _retrieval(session, language), session, language).reason


@pytest.mark.parametrize(
    "session, language, question",
    [
        ("AT", "en", "What is the Italian company policy on promoter commission?"),
        ("AT", "en", "what is the italian company policy on promoter commission?"),
        ("AT", "de", "What does the Italian local policy say about promoter commission?"),
        ("AT", "en", "What does the Italian Forever company policy say about returns?"),
        ("AT", "en", "Explain the Italian local company policies on returns."),
        ("DK", "da", "What is the Norwegian national policy on returns?"),
        ("AT", "de", "What is the Finnish company policy on returns?"),
        ("AT", "en", "What is the Dutch company policy on returns?"),
        ("SE", "sv", "What is the Luxembourgish company policy on returns?"),
        ("GB", "en", "What is the Canadian company policy on returns?"),
        ("DK", "en", "What is the German company policy on returns?"),
        ("IT", "it", "What is the Austrian company policy on returns?"),
        ("NL", "nl", "What is the Belgian company policy on returns?"),
        ("AT", "en", "What is the Danish company policy on returns?"),
        ("NO", "no", "What is the Swedish company policy on returns?"),
        ("FI", "fi", "What is the Serbian company policy on returns?"),
        ("CH", "de", "What is the Kyrgyz company policy on returns?"),
        ("BE", "fr", "What is the Mexican company policy on returns?"),
    ],
)
def test_policy_request_naming_another_market_by_adjective_is_refused(session, language, question) -> None:
    decision = approve_evidence(question, _retrieval(session, language), session, language)

    assert decision.approved is False
    assert decision.reason == "cross_market_policy_request"
    assert decision.evidence == []


@pytest.mark.parametrize(
    "session, question",
    [
        ("AT", "What is the Austrian company policy on promoter commission?"),
        ("RS", "What is the Serbian company policy on returns?"),
        ("GB", "What is the English company policy on returns?"),
        ("KG", "What is the English company policy on returns?"),
        # A language the session's own market is configured for may be asking
        # for a language version of the session's own policy.
        ("AT", "Is there a German company policy on returns?"),
        ("CH", "Is there an Italian company policy on returns?"),
        ("BE", "Is there a Dutch company policy on returns?"),
        ("BE", "Is there a French company policy on returns?"),
    ],
)
def test_own_market_adjective_or_own_language_keeps_answering(session, question) -> None:
    assert _reason(question, session) == "approved"


@pytest.mark.parametrize(
    "question",
    [
        "Can you explain the company policy on returns in Italian?",
        "Please answer in Italian: what does the company policy say about returns?",
        "Bitte auf Deutsch: what does the company policy say about returns?",
        "My Italian downline asks what the company policy on returns is.",
        "What is the company policy for Italian customers on returns?",
        "Is the Italian Aloe product covered by the company policy on returns?",
        "What does the Italianate company policy wording mean?",
        "What is the new company policy on returns?",
        "What is the local company policy on returns?",
    ],
)
def test_language_nationality_and_substring_mentions_do_not_refuse(question) -> None:
    assert _reason(question, "AT") == "approved"


@pytest.mark.parametrize(
    "question",
    ["Can I sponsor someone in Italy?", "Can I sponsor an Italian person into my downline?"],
)
def test_foreign_sponsoring_questions_keep_the_global_directory_evidence(question) -> None:
    decision = approve_evidence(question, _retrieval("AT", "en"), "AT", "en")

    assert decision.approved is True
    assert "GLOBAL:sponsoring-italy" in [document.id for document in decision.evidence]


def test_foreign_local_policy_rows_are_never_approved_evidence() -> None:
    """The layer below the refusal: another market's policy row never survives the gate."""
    foreign = _document("IT:4", "IT", "en", "country", "policy")
    decision = approve_evidence(
        "What commission does a Promoter earn on their orders?",
        _retrieval("AT", "en", foreign),
        "AT",
        "en",
    )

    assert decision.approved is True
    assert "IT:4" not in [document.id for document in decision.evidence]


def test_adjectives_are_not_market_mentions_and_not_typos() -> None:
    """find_market_mentions keeps its name-only contract; the typo path is untouched."""
    question = "What is the Italian company policy on promoter commission?"

    assert market_config.find_market_mentions(question) == set()
    assert market_config.find_probable_market_typo(question) is None
    assert market_config.find_probable_market_typo("What is the Itally company policy on commission?") == "Italy"


def test_adjective_recognition_is_derived_from_configured_market_names(monkeypatch) -> None:
    """A newly configured market is recognised without a code or word-list change."""
    monkeypatch.setattr(
        market_config,
        "load_market_config",
        lambda: {"markets": [{"code": "ZZ", "name": "Zembla", "enabled": True, "languages": []}]},
    )
    monkeypatch.setattr(market_config, "load_global_directory_markets", lambda: [])

    assert market_config.market_adjective_codes("Zemblan") == {"ZZ"}
    assert market_config.market_adjective_codes("Zemb") == set()


def test_published_policy_language_names_stand_in_for_irregular_adjectives() -> None:
    assert market_config.market_adjective_codes("Norwegian") == {"NO"}
    assert market_config.market_adjective_codes("Dutch") == {"BE", "NL"}
    assert market_config.market_adjective_codes("Dutch", "NL") == set()
    assert market_config.market_adjective_codes("German") == {"DE"}
    assert market_config.market_adjective_codes("German", "AT") == set()
    # A language no market publishes a policy in is not treated as a market.
    assert market_config.market_adjective_codes("Arabic") == set()


@pytest.mark.parametrize(
    "case_number, expected_reason",
    [("08", "cross_market_policy_request"), ("12", "approved"),
     ("22", "cross_market_policy_request"), ("23", "approved")],
)
def test_held_out_scope_cases_keep_their_gate_classification(case_number, expected_reason) -> None:
    """Regression only: the frozen pack's wording, read, never tuned to."""
    pack = json.loads(PACK_PATH.read_text(encoding="utf-8"))
    case = next(item for item in pack["cases"] if item["id"].startswith(f"ho-slp-{case_number}-"))

    assert _reason(case["question"], case["country"], case["language"]) == expected_reason


class _Governance:
    def evaluate(self, **_: object) -> GovernanceDecision:
        return GovernanceDecision(allowed=True, action=GovernanceAction.ALLOW, provider="test")


class _Validator:
    def validate(self, *_: object, **__: object) -> ValidationResult:
        return ValidationResult()


def test_orchestrator_gives_scope_copy_and_no_model_context_for_the_reported_question(monkeypatch) -> None:
    monkeypatch.setattr(chat_orchestrator, "append_session_turn", lambda *_: None)
    orchestrator = AIOrchestrator(validator=_Validator(), governance=_Governance())
    question = "What is the Italian company policy on promoter commission?"
    body = ChatRequest(message=question, sessionId="w5", country="AT", language="en")

    response, approved, decision = orchestrator._route_or_approve_evidence(
        question, _retrieval("AT", "en"), question, body, "cid"
    )

    assert decision is not None and decision.reason == "cross_market_policy_request"
    assert approved.documents == []
    assert response is not None and response.answer.startswith(CROSS_MARKET_POLICY_SCOPE_RESPONSE)


def test_orchestrator_still_answers_the_own_market_adjective_question(monkeypatch) -> None:
    monkeypatch.setattr(chat_orchestrator, "append_session_turn", lambda *_: None)
    orchestrator = AIOrchestrator(validator=_Validator(), governance=_Governance())
    question = "What is the Austrian company policy on promoter commission?"
    body = ChatRequest(message=question, sessionId="w5", country="AT", language="en")

    response, approved, decision = orchestrator._route_or_approve_evidence(
        question, _retrieval("AT", "en"), question, body, "cid"
    )

    assert decision is not None and decision.approved is True
    assert response is None
    assert [document.id for document in approved.documents] == ["AT:4.01"]
