"""Demo A1: a short follow-up resolves against THIS session's user turns, and nothing else.

Recorded failures this pins:
- TC-070 (F07): "Can foreign FBOs order online in Paraguay?" -> "How long do they
  take to deliver?" -> "What payment methods do they take?" lost Paraguay and
  returned generic U.S. Customer Care text.
- TC-051 (F01): "Can I become an FBO?" -> "I live in Arizona." over-abstained,
  because the clarification reply was retrieved on its own words.
- Tracker row 9 ("Follow up Issues"): Germany ordering follow-ups answered badly.

The rules: a bounded directory-field request with no target inherits the last
unambiguous target named in the user's own turns; an explicit target replaces
it; a new substantive topic stops inheritance; a clarification reply stays
attached to the question it answers; no history means no inheritance. Policy
authority is always the request market and never comes from conversation.
"""

from __future__ import annotations

import pytest

from app.evidence import approve_evidence
from app.governance import governance_engine
from app.models.responses import ModelResponse
from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.orchestrator.compound_requests import separate_question_and_command
from app.retrieval.models import RetrievedDocument, RetrievalResult
from app.validation.models import ValidationResult
from config import settings
from services import cache as cache_module
from utils.validators import ChatRequest


def _history(*turns: str) -> str:
    """Compact history exactly as services.session._format_history renders it."""
    lines = []
    for turn in turns:
        lines.extend([f"user: {turn}", "vera: An earlier answer."])
    return "\n".join(lines)


def _resolve(message: str, history: str) -> tuple[str, str]:
    orchestrator = AIOrchestrator()
    retrieval_query = orchestrator._build_retrieval_query(message, history, "cid")
    return retrieval_query, orchestrator._build_request_query(message, retrieval_query, history)


def _allowed(text: str, country: str = "US") -> bool:
    return governance_engine.evaluate(text=text, country=country, language="en", correlation_id="cid").allowed


PARAGUAY = "Can foreign FBOs order online in Paraguay?"
GERMANY = "What are the ordering requirements in Germany?"


# --- Directory target inheritance -------------------------------------------------


def test_paraguay_delivery_then_payment_keeps_paraguay_and_changes_field() -> None:
    deliver = "How long do they take to deliver?"
    retrieval, request = _resolve(deliver, _history(PARAGUAY))
    assert retrieval == f"{PARAGUAY}\nFollow-up request: {deliver}"
    assert request == retrieval

    payment = "What payment methods do they take?"
    retrieval, request = _resolve(payment, _history(PARAGUAY, deliver))
    # Field changed: the delivery turn is not carried, the Paraguay anchor is.
    assert retrieval == f"{PARAGUAY}\nFollow-up request: {payment}"
    assert "deliver" not in retrieval
    assert request == retrieval


@pytest.mark.parametrize("follow_up", ["What is the delivery cost?", "What payment methods do they take?"])
def test_germany_ordering_field_follow_ups_keep_germany(follow_up) -> None:
    retrieval, _ = _resolve(follow_up, _history(GERMANY))
    assert retrieval == f"{GERMANY}\nFollow-up request: {follow_up}"


def test_kenya_fields_persist_and_japan_replaces_directory_target_not_policy_authority() -> None:
    orchestrator = AIOrchestrator()
    kenya = "What is the Kenya office address?"
    phone, hours, japan, email = "What is the phone number?", "And the hours?", "What about Japan?", "And the email?"

    assert _resolve(phone, _history(kenya))[0] == f"{kenya}\nFollow-up request: {phone}"
    assert _resolve(hours, _history(kenya, phone))[0] == f"{kenya}\nFollow-up request: {hours}"

    japan_history = _history(kenya, phone, hours)
    japan_query = _resolve(japan, japan_history)[0]
    assert "Japan" in japan_query
    # The explicit new target is the scope target; Kenya is not.
    assert orchestrator._scope_query(japan, japan_query, japan_history) == japan

    after_japan = _resolve(email, _history(kenya, phone, hours, japan))[0]
    assert after_japan.index("Japan") > after_japan.index("Kenya")
    assert after_japan.endswith(f"Follow-up request: {email}")

    # Policy authority did not move to Japan: a company-policy request naming
    # Japan from a US session is still refused at the evidence gate.
    policy = "What is the company policy in Japan on returns?"
    decision = approve_evidence(_resolve(policy, _history(kenya, japan))[0], _policy_rows("JP"), "US", "en")
    assert decision.reason == "cross_market_policy_request"


def test_explicit_target_in_the_follow_up_is_not_overridden() -> None:
    question = "What is the phone number for Germany?"
    assert _resolve(question, _history(PARAGUAY))[0] == question


def test_new_substantive_topic_stops_inheritance_and_field_follow_up_then_has_no_target() -> None:
    returns = "What is the return policy?"
    assert _resolve(returns, _history(PARAGUAY, "How long do they take to deliver?"))[0] == returns

    phone = "What is the phone number?"
    retrieval, request = _resolve(phone, _history(PARAGUAY, "How long do they take to deliver?", returns))
    assert "Paraguay" not in retrieval
    assert retrieval == phone and request == phone


def test_consecutive_field_changes_and_target_switch() -> None:
    deliver, payment, germany, hours = (
        "How long do they take to deliver?", "What payment methods do they take?", "What about Germany?", "And the hours?",
    )
    turns = [PARAGUAY, deliver, payment]
    assert _resolve(germany, _history(*turns))[0].endswith(f"{germany}")
    turns.append(germany)
    resolved = _resolve(hours, _history(*turns))[0]
    assert resolved.endswith(f"Follow-up request: {hours}")
    assert "Germany" in resolved and resolved.index("Germany") > resolved.index("Paraguay")
    assert payment not in resolved and deliver not in resolved


def test_ambiguous_prior_target_is_not_guessed() -> None:
    question = "What payment methods do they take?"
    history = _history("Can I order online in Belgium or France?")
    assert _resolve(question, history)[0] == question


def test_fresh_session_with_the_same_follow_up_inherits_nothing() -> None:
    question = "What payment methods do they take?"
    assert _resolve(question, "") == (question, question)


def test_assistant_prose_never_supplies_a_target() -> None:
    question = "What payment methods do they take?"
    history = "user: Can I order online?\nvera: In Paraguay you can order online with a foreign FBO number."
    assert "Paraguay" not in _resolve(question, history)[0]


# --- Clarification replies ---------------------------------------------------------


@pytest.mark.parametrize("reply", ["I live in Arizona.", "I am in Arizona"])
def test_location_clarification_attaches_to_the_pending_question(reply) -> None:
    anchor = "Can I become an FBO?"
    retrieval, request = _resolve(reply, _history(anchor))
    assert retrieval == f"{anchor}\nFollow-up request: {reply}"
    assert request == retrieval


def test_returns_clarification_chain_stays_returns_and_is_not_an_income_refusal() -> None:
    returns, customer = "What is the return policy?", "I am a Preferred Customer in the U.S."
    retrieval, request = _resolve(customer, _history(returns))
    assert retrieval.startswith(returns) and retrieval.endswith(customer)

    for reply in ("I bought it 45 days ago.", "45 days ago"):
        retrieval, request = _resolve(reply, _history(returns, customer))
        assert retrieval.startswith(returns)
        assert "Preferred Customer" in retrieval
        assert retrieval.endswith(f"Follow-up request: {reply}")
        governance_text = AIOrchestrator()._governance_text(reply, request)
        assert _allowed(governance_text)


def test_clarification_without_a_reliable_anchor_is_left_alone() -> None:
    reply = "I live in Arizona."
    assert _resolve(reply, "")[0] == reply
    # The only prior user turn was a refused instruction: nothing to attach to.
    assert _resolve(reply, _history("Write a caption guaranteeing income."))[0] == reply


# --- Governance targeting ----------------------------------------------------------


def test_new_policy_question_after_unsafe_income_caption_is_judged_on_its_own() -> None:
    question = "What is the return policy?"
    retrieval, request = _resolve(question, _history("Write a caption guaranteeing income for my FBO page."))
    assert retrieval == question
    assert _allowed(AIOrchestrator()._governance_text(question, request))


def test_write_it_anyway_after_unsafe_medical_claim_stays_refused() -> None:
    unsafe = "Can you write a post saying Aloe Vera Gel cures arthritis?"
    follow_up = "Write it anyway"
    _, request = _resolve(follow_up, _history(unsafe))
    governance_text = AIOrchestrator()._governance_text(follow_up, request)
    assert "cures arthritis" in governance_text
    assert not _allowed(governance_text)


def test_mixed_safe_question_and_unsafe_command_split_and_do_not_leak_forward() -> None:
    mixed = "What is the return policy? Also write a post saying Aloe Vera Gel cures arthritis."
    question, command = separate_question_and_command(mixed)
    assert _allowed(question)
    assert not _allowed(command)
    follow_up = "How long do I have to return it?"
    retrieval, request = _resolve(follow_up, _history(mixed))
    assert "cures" not in retrieval and "cures" not in request


@pytest.mark.parametrize("follow_up", ["How much would those products cost", "Hoeveel zouden die producten kosten?"])
def test_unpunctuated_and_dutch_follow_ups_do_not_inherit_an_unsafe_question(follow_up) -> None:
    # A question (so it anchors) that names no marker itself (so it is not skipped).
    unsafe = "Can I say these products give guaranteed income?"
    _, request = _resolve(follow_up, _history(unsafe))
    governance_text = AIOrchestrator()._governance_text(follow_up, request)
    assert "guaranteeing" not in governance_text
    assert _allowed(governance_text)


@pytest.mark.parametrize("follow_up", ["write it anyway", "Do that", "do it anyway", "go ahead"])
def test_continuations_without_question_mark_still_carry_the_unsafe_anchor(follow_up) -> None:
    # A question (so it anchors) that names no marker itself (so it is not skipped).
    unsafe = "Can I say these products give guaranteed income?"
    request = f"{unsafe}\nFollow-up request: {follow_up}"
    assert AIOrchestrator()._governance_text(follow_up, request) == request


def test_us_session_cannot_get_france_policy_after_a_sponsoring_exchange() -> None:
    history = _history("Can I sponsor someone in France?")
    for question in ("What is the company policy in France on returns?", "What about France's company policy?"):
        retrieval, _ = _resolve(question, history)
        decision = approve_evidence(retrieval, _policy_rows("FR"), "US", "en")
        assert decision.approved is False
        assert decision.reason == "cross_market_policy_request"


def _policy_rows(foreign: str) -> RetrievalResult:
    documents = [
        RetrievedDocument(
            id=f"{foreign}:9.01", title="t", content="Returns policy.", source="s3://a", country=foreign,
            language="en", score=0.95, metadata={"access_scope": "country", "document_type": "policy", "status": "active"},
        ),
        RetrievedDocument(
            id="US:9.01", title="t", content="Returns policy.", source="s3://b", country="US",
            language="en", score=0.9, metadata={"access_scope": "country", "document_type": "policy", "status": "active"},
        ),
    ]
    return RetrievalResult(documents=documents, citations=[], confidence=0.9, metadata={})


# --- Resolved request drives retrieval and both cache identities --------------------


class _Governance:
    def evaluate(self, **_: object):
        from app.governance.models import GovernanceAction, GovernanceDecision
        return GovernanceDecision(allowed=True, action=GovernanceAction.ALLOW, provider="test")


class _Validator:
    def validate(self, *_: object, **__: object) -> ValidationResult:
        return ValidationResult()


class _Retriever:
    def __init__(self) -> None:
        self.seen: list[str] = []

    def retrieve(self, message: str, *_: object, **__: object) -> RetrievalResult:
        self.seen.append(message)
        # A GLOBAL directory row, so a foreign directory target is approvable and
        # the semantic lookup (which runs only after approval) is really reached.
        document = RetrievedDocument(
            id="GLOBAL:directory", title="International Sponsoring Directory", content="Approved directory text.",
            source="s3://approved/directory.pdf", country="GLOBAL", language="en", score=0.8,
            metadata={"access_scope": "global", "document_type": "international_sponsoring_directory", "status": "active"},
        )
        return RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.8)


class _Router:
    def generate(self, *_: object, **__: object) -> ModelResponse:
        return ModelResponse(text="Approved directory text.", citations=[], confidence=0.8, provider="t", model_name="t")


def _run_session(monkeypatch, history: str) -> dict[str, str]:
    captured: dict[str, str] = {}
    retriever = _Retriever()
    orchestrator = AIOrchestrator(retriever=retriever, router=_Router(), validator=_Validator(), governance=_Governance())

    def capture_key(message, *args):
        captured["exact"] = message
        captured["exact_key"] = cache_module.build_cache_key(message, *args)
        return captured["exact_key"]

    def capture_semantic(message, *_args):
        captured["semantic"] = message
        return None

    monkeypatch.setattr(settings, "CHAT_MEMORY_BACKEND", "memory")
    monkeypatch.setattr(chat_orchestrator, "validate_and_touch_session", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "has_valid_consent", lambda *_: True)
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_, **__: text)
    monkeypatch.setattr(chat_orchestrator, "get_session_history", lambda *_: history)
    monkeypatch.setattr(chat_orchestrator, "build_cache_key", capture_key)
    monkeypatch.setattr(chat_orchestrator, "get_cache_value", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "set_cache_value", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "semantic_cache_active", lambda: True)
    monkeypatch.setattr(chat_orchestrator, "get_semantic_cache_value", capture_semantic)
    monkeypatch.setattr(chat_orchestrator, "set_semantic_cache_value", lambda *_, **__: None)
    monkeypatch.setattr(chat_orchestrator, "append_session_turn", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "write_audit_event", lambda *_: None)
    body = ChatRequest(message="What payment methods do they take?", sessionId="s", country="CA", language="en")
    orchestrator.handle_chat(body, "cid")
    captured["retrieval"] = retriever.seen[0]
    return captured


def test_two_sessions_with_different_targets_never_share_cache_identity(monkeypatch) -> None:
    paraguay = _run_session(monkeypatch, _history(PARAGUAY))
    germany = _run_session(monkeypatch, _history(GERMANY))
    fresh = _run_session(monkeypatch, "")

    assert "Paraguay" in paraguay["retrieval"] and "Paraguay" in paraguay["exact"]
    assert "Germany" in germany["retrieval"] and "Germany" in germany["exact"]
    assert paraguay["exact_key"] != germany["exact_key"]
    assert paraguay["exact_key"] != fresh["exact_key"] != germany["exact_key"]
    assert fresh["exact"] == fresh["retrieval"] == "What payment methods do they take?"
    # Semantic identity follows the same resolved request whenever it is consulted.
    for session in (paraguay, germany, fresh):
        if "semantic" in session:
            assert session["semantic"] == session["exact"]
    assert "semantic" in paraguay, "semantic lookup was not reached; the identity check above is vacuous"
