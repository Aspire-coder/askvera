"""CX wiring: every delivered response carries exactly one typed outcome.

Drives the real AIOrchestrator.handle_chat offline (fake retriever, router,
validator and governance; session, cache and audit monkeypatched), the same
harness shape as tests/conversation_pack/test_conversation_pack.py.
"""

from __future__ import annotations

import json

import pytest

from app.governance.models import GovernanceAction, GovernanceDecision
from app.models.responses import ModelResponse
from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.retrieval.models import RetrievalAvailability, RetrievalResult, RetrievedDocument
from app.validation.models import ValidationResult
from config import settings
from utils.validators import ChatRequest

KENYA_CONTENT = (
    "Forever Kenya/East Africa\n"
    "• Delivery Cost: $3 within the country.\n"
    "• Payment methods accepted: Bank deposit, Credit Card, Mobile Money Transfer (Mpesa).\n"
    "Telephone Office +254 20 2026869\n"
)


class _Governance:
    def evaluate(self, **_: object) -> GovernanceDecision:
        return GovernanceDecision(allowed=True, action=GovernanceAction.ALLOW, provider="test")


class _Validator:
    def validate(self, *_: object, **__: object) -> ValidationResult:
        return ValidationResult()


class _Router:
    def __init__(self, text: str) -> None:
        self.text = text

    def generate(self, *_: object, **__: object) -> ModelResponse:
        return ModelResponse(text=self.text, citations=[], confidence=0.8, provider="t", model_name="t")


class _Retriever:
    def __init__(self, documents: list[RetrievedDocument], availability=RetrievalAvailability.AVAILABLE) -> None:
        self.documents = documents
        self.availability = availability

    def retrieve(self, *_: object, **__: object) -> RetrievalResult:
        return RetrievalResult(
            documents=list(self.documents),
            citations=[document.to_source() for document in self.documents],
            confidence=0.8 if self.documents else 0.0,
            availability=self.availability,
        )


def _kenya_directory_row() -> RetrievedDocument:
    return RetrievedDocument(
        id="GLOBAL:kenya", title="International-Sponsoring-Directory.pdf", content=KENYA_CONTENT,
        source="International-Sponsoring-Directory.pdf", country="GLOBAL", language="en", score=0.9,
        metadata={
            "directory_kind": "international_sponsoring", "directory_section": "sponsoring",
            "record_country": "Kenya/East Africa", "access_scope": "global",
            "document_type": "international_sponsoring_directory", "status": "active", "section_id": "kenya",
        },
    )


@pytest.fixture
def run(monkeypatch):
    monkeypatch.setattr(settings, "CHAT_MEMORY_BACKEND", "memory")
    for name, value in {
        "validate_and_touch_session": lambda *_: None,
        "has_valid_consent": lambda *_: True,
        "scrub_pii": lambda text, *_, **__: text,
        "get_session_history": lambda *_: "",
        "get_cache_value": lambda *_: None,
        "set_cache_value": lambda *_: None,
        "semantic_cache_active": lambda: False,
        "append_session_turn": lambda *_: None,
        "write_audit_event": lambda *_: None,
    }.items():
        monkeypatch.setattr(chat_orchestrator, name, value)

    def _run(message, documents, *, country="US", language="en", answer="Approved text.", availability=None):
        retriever = _Retriever(documents, availability or RetrievalAvailability.AVAILABLE)
        orchestrator = AIOrchestrator(
            retriever=retriever, router=_Router(answer), validator=_Validator(), governance=_Governance()
        )
        body = ChatRequest(message=message, sessionId="s", country=country, language=language)
        return orchestrator.handle_chat(body, "cid")

    return _run


def test_retrieval_unavailable_is_a_dependency_outcome_carrying_availability(run):
    response = run("What payment methods does Forever Kenya accept?", [], availability=RetrievalAvailability.UNAVAILABLE)
    outcome = response.metadata["outcome"]
    assert outcome["kind"] == "dependency_unavailable"
    assert outcome["failure_layer"] == response.metadata["failure_layer"] == "dependency_unavailable"
    assert outcome["retrieval_availability"] == "unavailable"


def test_no_evidence_is_an_evidence_missing_outcome(run):
    response = run("What is the refund window for damaged products?", [])
    assert response.metadata["outcome"]["kind"] == "evidence_missing"


def test_other_market_directory_answer_is_international_and_names_the_target(run):
    response = run(
        "What payment methods does Forever Kenya accept?", [_kenya_directory_row()],
        answer="Forever Kenya accepts bank deposit, credit card and Mpesa.",
    )
    outcome = response.metadata["outcome"]
    # Classified from the approved evidence the turn actually used; the target
    # is the record's own market, never the session market.
    assert outcome["kind"] == "international_directory", response.metadata
    assert outcome["directory_target"] == "Kenya/East Africa"
    assert "payment_methods" in outcome["fields_requested"]


@pytest.mark.parametrize("documents,availability", [
    ([], RetrievalAvailability.UNAVAILABLE),
    ([], RetrievalAvailability.AVAILABLE),
    ("kenya", RetrievalAvailability.AVAILABLE),
])
def test_cx_only_appends_whole_paragraphs_and_never_alters_citations_or_existing_metadata(run, documents, availability):
    """With the composer wired, CX may ADD paragraphs (and strip a pure
    preamble, which these answers do not have). It never rewrites the delivered
    answer, never touches citations and never changes an existing metadata key."""
    docs = [_kenya_directory_row()] if documents == "kenya" else documents
    kwargs = dict(answer="Forever Kenya accepts bank deposit, credit card and Mpesa.", availability=availability)
    original = chat_orchestrator.AIOrchestrator._attach_conversation_outcome
    chat_orchestrator.AIOrchestrator._attach_conversation_outcome = lambda self, response, body, question: response
    try:
        without = run("What payment methods does Forever Kenya accept?", docs, **kwargs)
    finally:
        chat_orchestrator.AIOrchestrator._attach_conversation_outcome = original
    with_cx = run("What payment methods does Forever Kenya accept?", docs, **kwargs)
    assert with_cx.answer == without.answer or with_cx.answer.startswith(without.answer + "\n\n")
    assert with_cx.citations == without.citations
    added = {"outcome", "cx_applied"}
    assert {k: v for k, v in with_cx.metadata.items() if k not in added} == without.metadata
    assert isinstance(with_cx.metadata["cx_applied"], list)


def test_turn_evidence_does_not_leak_into_the_next_turn(run):
    first = run("What payment methods does Forever Kenya accept?", [_kenya_directory_row()],
                answer="Forever Kenya accepts bank deposit, credit card and Mpesa.")
    assert first.metadata["outcome"]["directory_target"] == "Kenya/East Africa"
    second = run("What is the refund window for damaged products?", [])
    assert second.metadata["outcome"]["directory_target"] is None


def test_a_stale_decision_outside_the_turn_is_ignored_and_restored(run):
    # Plant a stale approved decision (as a direct unit call of
    # _route_or_approve_evidence would leave behind), then run a turn that
    # approves nothing: the turn must not see it, and must restore it on exit.
    first = run("What payment methods does Forever Kenya accept?", [_kenya_directory_row()],
                answer="Forever Kenya accepts bank deposit, credit card and Mpesa.")
    assert first.metadata["outcome"]["kind"] == "international_directory"
    stale = chat_orchestrator.EvidenceDecision(
        approved=True, reason="approved", evidence=[_kenya_directory_row()], query_intent="policy_fact",
        exact_topic_match=True, top_score=0.9, score_margin=0.9,
    )
    token = chat_orchestrator._TURN_EVIDENCE.set(stale)
    try:
        response = run("What is the refund window for damaged products?", [])
        assert response.metadata["outcome"]["kind"] == "evidence_missing"
        assert response.metadata["outcome"]["directory_target"] is None
        assert chat_orchestrator._TURN_EVIDENCE.get() is stale
    finally:
        chat_orchestrator._TURN_EVIDENCE.reset(token)


def test_outcome_metadata_is_json_serialisable(run):
    response = run("What payment methods does Forever Kenya accept?", [_kenya_directory_row()],
                   answer="Forever Kenya accepts bank deposit, credit card and Mpesa.")
    json.dumps(response.metadata["outcome"])


def test_non_english_request_keeps_its_language_on_the_outcome(run):
    response = run("¿Qué métodos de pago acepta Forever Kenya?", [_kenya_directory_row()], language="es",
                   answer="Forever Kenya acepta depósito bancario, tarjeta de crédito y Mpesa.")
    outcome = response.metadata["outcome"]
    assert outcome["language"] == "es"
    assert "payment_methods" in outcome["fields_requested"]


def test_cross_market_refusal_names_the_market_and_never_ships_a_placeholder(run, monkeypatch):
    errors = []
    monkeypatch.setattr(chat_orchestrator.LOGGER, "error", lambda event, **_: errors.append(event))
    response = run("What is the company policy in Sweden on returns?", [])
    outcome = response.metadata["outcome"]
    assert outcome["kind"] == "cross_market_policy"
    assert "Sweden" in response.answer
    assert "{" not in response.answer
    assert "cx_unfilled_placeholder_delivered" not in errors


def test_an_unfilled_placeholder_is_logged_not_rewritten(run, monkeypatch):
    errors = []
    monkeypatch.setattr(chat_orchestrator.LOGGER, "error", lambda event, **_: errors.append(event))
    response = run("What payment methods does Forever Kenya accept?", [_kenya_directory_row()],
                   answer="For {country}, Forever Kenya accepts bank deposit.")
    assert "cx_unfilled_placeholder_delivered" in errors
    assert "{country}" in response.answer  # logged, never silently rewritten


class _RecordingRetriever(_Retriever):
    def __init__(self, documents):
        super().__init__(documents)
        self.calls = []

    def retrieve(self, message, country, language, *args, **kwargs):
        self.calls.append((country, language))
        return super().retrieve()


def test_answer_language_switch_never_changes_retrieval_eligibility_or_shares_a_cache_key(monkeypatch):
    """Approval 6 option B: presentation follows the message; eligibility never does."""
    monkeypatch.setattr(settings, "CHAT_MEMORY_BACKEND", "memory")
    for name, value in {
        "validate_and_touch_session": lambda *_: None, "has_valid_consent": lambda *_: True,
        "scrub_pii": lambda text, *_, **__: text, "get_session_history": lambda *_: "",
        "get_cache_value": lambda *_: None, "set_cache_value": lambda *_: None,
        "semantic_cache_active": lambda: False, "append_session_turn": lambda *_: None,
        "write_audit_event": lambda *_: None,
    }.items():
        monkeypatch.setattr(chat_orchestrator, name, value)
    approvals, cache_keys, prompt_languages = [], [], []
    real_approve = chat_orchestrator.approve_evidence
    monkeypatch.setattr(chat_orchestrator, "approve_evidence",
                        lambda q, r, country, language: approvals.append((country, language)) or real_approve(q, r, country, language))
    monkeypatch.setattr(chat_orchestrator, "build_cache_key",
                        lambda q, country, language, role: cache_keys.append(language) or f"{q}|{country}|{language}|{role}")

    def _run(message, widget_language):
        retriever = _RecordingRetriever([_kenya_directory_row()])
        orchestrator = AIOrchestrator(retriever=retriever, router=_Router("Forever Kenya accepts Mpesa."),
                                      validator=_Validator(), governance=_Governance())
        real_build = orchestrator.prompt_builder.build
        orchestrator.prompt_builder.build = lambda *a, **k: prompt_languages.append(k.get("language")) or real_build(*a, **k)
        body = ChatRequest(message=message, sessionId="s", country="US", language=widget_language)
        return orchestrator.handle_chat(body, "cid"), retriever

    # A question that clearly switches today; Lane 7 is improving recall on
    # questions containing brand and market names (e.g. "…par Forever Kenya ?").
    switched, retriever = _run("Comment est-ce que je peux payer ma commande chez Forever Kenya ?", "en")
    assert switched.metadata["answer_language"]["answer"] == "fr"
    assert switched.metadata["outcome"]["language"] == "fr"
    assert retriever.calls and all(language == "en" for _, language in retriever.calls)
    assert approvals and all(language == "en" for _, language in approvals)
    assert prompt_languages[-1] == "fr"
    assert cache_keys[-1] == "en>fr"

    unswitched, retriever = _run("What payment methods does Forever Kenya accept?", "en")
    assert "answer_language" not in unswitched.metadata
    assert all(language == "en" for _, language in retriever.calls)
    assert prompt_languages[-1] == "en"
    assert cache_keys[-1] == "en"
    assert chat_orchestrator._ANSWER_LANGUAGE.get() is None


def test_a_composer_failure_never_breaks_the_turn(run, monkeypatch):
    def _boom(*_, **__):
        raise RuntimeError("composer bug")

    monkeypatch.setattr(chat_orchestrator, "compose_cx_response", _boom)
    response = run("What payment methods does Forever Kenya accept?", [_kenya_directory_row()],
                   answer="Forever Kenya accepts bank deposit, credit card and Mpesa.")
    assert response.answer == "Forever Kenya accepts bank deposit, credit card and Mpesa."
    assert response.metadata["outcome"]["kind"] in {"international_directory", "partial_answer", "answer"}
    assert response.metadata["cx_applied"] == []


def _repair_harness(monkeypatch, history):
    monkeypatch.setattr(settings, "CHAT_MEMORY_BACKEND", "memory")
    persisted = []
    for name, value in {
        "validate_and_touch_session": lambda *_: None, "has_valid_consent": lambda *_: True,
        "scrub_pii": lambda text, *_, **__: text, "get_session_history": lambda *_: history,
        "get_cache_value": lambda *_: None, "set_cache_value": lambda *_: None,
        "semantic_cache_active": lambda: False,
        "append_session_turn": lambda session, message, *_: persisted.append(message),
        "write_audit_event": lambda *_: None,
    }.items():
        monkeypatch.setattr(chat_orchestrator, name, value)
    return persisted


class _QueryRecordingRetriever(_Retriever):
    def __init__(self, documents):
        super().__init__(documents)
        self.queries = []

    def retrieve(self, message, country, *args, **kwargs):
        self.queries.append((message, country))
        return super().retrieve()


def test_a_repair_rewrites_retrieval_persists_the_original_and_keeps_the_policy_country(monkeypatch):
    persisted = _repair_harness(monkeypatch, "user: What are the payment methods in Kenya?\nvera: An earlier answer.")
    retriever = _QueryRecordingRetriever([_kenya_directory_row()])
    orchestrator = AIOrchestrator(retriever=retriever, router=_Router("Approved text."),
                                  validator=_Validator(), governance=_Governance())
    body = ChatRequest(message="No, I meant Ghana", sessionId="s", country="US", language="en")
    response = orchestrator.handle_chat(body, "cid")
    assert response.metadata["conversation_repair"] == {"kind": "market", "replacement": "Ghana"}
    assert any("Ghana" in query for query, _ in retriever.queries)
    assert all(country == "US" for _, country in retriever.queries)
    assert persisted == ["No, I meant Ghana"]


@pytest.mark.parametrize("message,language", [
    ("What is the shoping cost?", "en"),
    ("¿Cuál es el costo de shoping?", "es"),
])
def test_an_ambiguous_typo_asks_one_question_and_never_retrieves(monkeypatch, message, language):
    _repair_harness(monkeypatch, "")
    retriever = _QueryRecordingRetriever([_kenya_directory_row()])
    orchestrator = AIOrchestrator(retriever=retriever, router=_Router("Approved text."),
                                  validator=_Validator(), governance=_Governance())
    response = orchestrator.handle_chat(ChatRequest(message=message, sessionId="s", country="US", language=language), "cid")
    assert response.metadata["outcome"]["kind"] == "clarification"
    assert response.metadata["failure_layer"] == "typo_clarification"
    assert retriever.queries == []
    assert response.answer.count("?") == 1
    assert "{" not in response.answer
    assert response.metadata["cx_applied"] == []


@pytest.mark.parametrize("message", ["What is the shipping cost?", "How much is the shipping?", "No minimum order?"])
def test_correct_words_and_plain_negatives_never_clarify_or_repair(monkeypatch, message):
    _repair_harness(monkeypatch, "user: What are the payment methods in Kenya?\nvera: An earlier answer.")
    retriever = _QueryRecordingRetriever([])
    orchestrator = AIOrchestrator(retriever=retriever, router=_Router("Approved text."),
                                  validator=_Validator(), governance=_Governance())
    response = orchestrator.handle_chat(ChatRequest(message=message, sessionId="s", country="US", language="en"), "cid")
    assert response.metadata.get("failure_layer") != "typo_clarification"
    assert "conversation_repair" not in response.metadata
    assert retriever.queries


def test_international_directory_note_only_when_the_question_asked_for_directory_fields(monkeypatch):
    _repair_harness(monkeypatch, "")

    def _answer(message, answer):
        orchestrator = AIOrchestrator(retriever=_Retriever([_kenya_directory_row()]), router=_Router(answer),
                                      validator=_Validator(), governance=_Governance())
        return orchestrator.handle_chat(ChatRequest(message=message, sessionId="s", country="US", language="en"), "cid")

    personal = _answer("Where is my order?", "Orders are usually delivered within 5 business days.")
    assert "personal_account_limit" in personal.metadata["cx_applied"]
    assert "international_directory_note" not in personal.metadata["cx_applied"]
    field = _answer("What is the phone number?", "The office phone is +254 20 2026869.")
    assert field.metadata["outcome"]["kind"] == "international_directory"
    assert "international_directory_note" in field.metadata["cx_applied"]
    assert "Kenya" in field.answer
