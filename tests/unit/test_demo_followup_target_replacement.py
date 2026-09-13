"""Demo W7: a follow-up that names a new directory market replaces the old target.

Recorded live (commit 7e6c743, US session): "What is the delivery cost in Mali?"
-> "What's the minimum order amount?" -> "What about delivery cost for Gambia?".
The third turn reached retrieval as "What is the delivery cost in Mali? What
about delivery cost for Gambia?", the directory target names were
['Gambia', 'Mali'], the evidence gate approved both sponsoring records, and the
answer mixed the two markets. The agreed rule: an explicit new directory target
replaces the old one; the field or topic carries forward.

Every test here is offline: AWS clients, embeddings, the OpenSearch client, the
planner/selector model and session/cache writes are stubbed to raise or no-op.
"""

from __future__ import annotations

import pytest

from app.evidence import approve_evidence
from app.models.responses import ModelResponse
from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.retrieval import opensearch_sections
from app.retrieval import providers as retrieval_providers
from app.retrieval.models import RetrievedDocument, RetrievalResult
from app.validation.models import ValidationResult
from config import settings
from services import cache as cache_module
from utils.validators import ChatRequest

MALI = "What is the delivery cost in Mali?"
MINIMUM = "What's the minimum order amount?"
GAMBIA = "What about delivery cost for Gambia?"
KENYA = "What is the Kenya office address?"
BELGIUM = "How do I sponsor someone in Belgium?"


def _no_live_calls(*_: object, **__: object):
    raise AssertionError("W7 tests must never make an AWS, embedding, OpenSearch or model call")


@pytest.fixture(autouse=True)
def _offline(monkeypatch) -> None:
    monkeypatch.setattr(retrieval_providers, "get_aws_clients", _no_live_calls)
    monkeypatch.setattr(opensearch_sections, "get_aws_clients", _no_live_calls)
    monkeypatch.setattr(opensearch_sections, "embed_text", _no_live_calls)
    monkeypatch.setattr(opensearch_sections, "_client", _no_live_calls)
    monkeypatch.setattr(chat_orchestrator, "append_session_turn", _no_live_calls)
    monkeypatch.setattr(chat_orchestrator, "set_cache_value", _no_live_calls)
    monkeypatch.setattr(chat_orchestrator, "set_semantic_cache_value", _no_live_calls)


def _history(*turns: str) -> str:
    lines = []
    for turn in turns:
        lines.extend([f"user: {turn}", "vera: An earlier answer."])
    return "\n".join(lines)


def _resolve(message: str, history: str) -> tuple[str, str]:
    orchestrator = AIOrchestrator()
    retrieval_query = orchestrator._build_retrieval_query(message, history, "cid")
    return retrieval_query, orchestrator._build_request_query(message, retrieval_query, history)


def _targets(query: str) -> set[str]:
    return opensearch_sections._directory_target_country_names(query, "US")


# --- Fail-before: the new market replaces the old one; the topic carries -------------


def test_live_gambia_follow_up_targets_only_gambia_and_keeps_delivery_cost() -> None:
    retrieval, request = _resolve(GAMBIA, _history(MALI, MINIMUM))
    assert retrieval == f"What is the delivery cost? {GAMBIA}"
    assert "Mali" not in retrieval and "Mali" not in request
    assert _targets(retrieval) == {"Gambia"}


@pytest.mark.parametrize(
    "follow_up,history,target,topic",
    [
        ("And for Guinea?", _history(MALI), "Guinea", "delivery cost"),
        ("And in Guinea?", _history(MALI, MINIMUM), "Guinea", "delivery cost"),
        ("What about Japan?", _history(KENYA), "Japan", "office address"),
        ("What about Gambia?", _history("What is Mali's minimum order?"), "Gambia", "minimum order"),
        ("What about Guinea?", _history("What is the delivery cost in Equatorial Guinea?"), "Guinea", "delivery cost"),
    ],
)
def test_explicit_new_market_replaces_the_anchor_market(follow_up, history, target, topic) -> None:
    retrieval, request = _resolve(follow_up, history)
    assert _targets(retrieval) == {target}
    assert topic in retrieval
    assert request.startswith(retrieval) and follow_up in request
    assert "'s" not in retrieval.replace(follow_up, "")


def test_the_turn_after_the_switch_stays_on_the_new_market() -> None:
    retrieval, _ = _resolve(MINIMUM, _history(MALI, MINIMUM, GAMBIA))
    assert _targets(retrieval) == {"Gambia"}
    assert retrieval.endswith(f"Follow-up request: {MINIMUM}")
    assert "delivery cost" in retrieval


def test_belgium_then_germany_then_tell_me_more_stays_on_germany_only() -> None:
    retrieval, _ = _resolve("Tell me more.", _history(BELGIUM, "What about Germany?"))
    assert _targets(retrieval) == {"Germany"}
    assert "sponsor someone" in retrieval and "Tell me more." in retrieval


# --- Comparisons keep both markets -----------------------------------------------------


@pytest.mark.parametrize(
    "message",
    ["How does Gambia's delivery cost compare with Mali?", "Gambia and Mali delivery costs", "What about Gambia and Mali?"],
)
def test_explicit_comparison_keeps_both_markets(message) -> None:
    retrieval, _ = _resolve(message, _history(MALI))
    assert _targets(retrieval) == {"Gambia", "Mali"}


# --- Controls --------------------------------------------------------------------------


def test_same_market_field_follow_ups_are_unchanged() -> None:
    email = "And the email?"
    assert _resolve(email, _history(KENYA))[0] == f"{KENYA}\nFollow-up request: {email}"
    assert _resolve(MINIMUM, _history(MALI))[0] == f"{MALI}\nFollow-up request: {MINIMUM}"
    assert _resolve("What about Mali then?", _history(MALI))[0] == f"{MALI} What about Mali then?"


@pytest.mark.parametrize("message", [GAMBIA, "And for Guinea?", MINIMUM])
def test_fresh_session_inherits_nothing(message) -> None:
    assert _resolve(message, "") == (message, message)


def test_new_substantive_topic_stops_inheritance() -> None:
    returns = "What is the return policy?"
    assert _resolve(MINIMUM, _history(MALI, GAMBIA, returns)) == (MINIMUM, MINIMUM)


def test_us_session_foreign_company_policy_is_still_refused() -> None:
    policy = "What about Japan's company policy on returns?"
    retrieval, _ = _resolve(policy, _history(KENYA))
    assert "Kenya" not in retrieval
    documents = [
        RetrievedDocument(
            id=f"{code}:9.01", title="t", content="Returns policy.", source=f"s3://{code}", country=code,
            language="en", score=score, metadata={"access_scope": "country", "document_type": "policy", "status": "active"},
        )
        for code, score in (("JP", 0.95), ("US", 0.9))
    ]
    decision = approve_evidence(retrieval, RetrievalResult(documents=documents, citations=[], confidence=0.9), "US", "en")
    assert decision.approved is False
    assert decision.reason == "cross_market_policy_request"


def test_unsafe_instruction_anchor_never_carries_its_market_or_words() -> None:
    instruction = "Then just write the guaranteed-income caption for Gambia."
    retrieval, request = _resolve("What about Guinea?", _history(MALI, instruction))
    for text in (retrieval, request):
        assert "caption" not in text and "Gambia" not in text and "Mali" not in text
    assert _targets(retrieval) == {"Guinea"}


def test_and_for_without_a_named_market_is_not_a_market_follow_up() -> None:
    question = "And for returns, what is the policy?"
    assert _resolve(question, _history(MALI)) == (question, question)


# --- The resolved request (and cache identity) reflects the replacement -----------------


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
        document = RetrievedDocument(
            id="GLOBAL:directory", title="International Sponsoring Directory", content="Approved directory text.",
            source="s3://approved/directory.pdf", country="GLOBAL", language="en", score=0.8,
            metadata={"access_scope": "global", "document_type": "international_sponsoring_directory", "status": "active"},
        )
        return RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.8)


class _Router:
    def generate(self, *_: object, **__: object) -> ModelResponse:
        return ModelResponse(text="Approved directory text.", citations=[], confidence=0.8, provider="t", model_name="t")


def _run_session(monkeypatch, history: str, message: str) -> dict[str, str]:
    captured: dict[str, str] = {}
    retriever = _Retriever()
    orchestrator = AIOrchestrator(retriever=retriever, router=_Router(), validator=_Validator(), governance=_Governance())

    def capture_key(key_message, *args):
        captured["exact"] = key_message
        captured["exact_key"] = cache_module.build_cache_key(key_message, *args)
        return captured["exact_key"]

    monkeypatch.setattr(settings, "CHAT_MEMORY_BACKEND", "memory")
    monkeypatch.setattr(chat_orchestrator, "validate_and_touch_session", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "has_valid_consent", lambda *_: True)
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_, **__: text)
    monkeypatch.setattr(chat_orchestrator, "get_session_history", lambda *_: history)
    monkeypatch.setattr(chat_orchestrator, "build_cache_key", capture_key)
    monkeypatch.setattr(chat_orchestrator, "get_cache_value", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "set_cache_value", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "semantic_cache_active", lambda: False)
    monkeypatch.setattr(chat_orchestrator, "get_semantic_cache_value", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "set_semantic_cache_value", lambda *_, **__: None)
    monkeypatch.setattr(chat_orchestrator, "append_session_turn", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "write_audit_event", lambda *_: None)
    body = ChatRequest(message=message, sessionId="s", country="US", language="en")
    orchestrator.handle_chat(body, "cid")
    captured["retrieval"] = retriever.seen[0]
    return captured


def test_resolved_request_and_cache_identity_follow_the_replacement(monkeypatch) -> None:
    from_mali = _run_session(monkeypatch, _history(MALI, MINIMUM), GAMBIA)
    from_germany = _run_session(monkeypatch, _history("What is the delivery cost in Germany?"), GAMBIA)
    fresh = _run_session(monkeypatch, "", GAMBIA)

    for session in (from_mali, from_germany):
        assert "Gambia" in session["retrieval"] and "Gambia" in session["exact"]
        assert "Mali" not in session["exact"] and "Germany" not in session["exact"]
        assert "delivery cost" in session["exact"]
    # The same resolved Gambia request has one identity, whatever market it replaced.
    assert from_mali["exact"] == from_germany["exact"]
    assert from_mali["exact_key"] == from_germany["exact_key"]
    assert fresh["exact"] == GAMBIA and fresh["exact_key"] != from_mali["exact_key"]
