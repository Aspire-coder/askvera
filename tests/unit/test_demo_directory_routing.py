"""Demo W4: a short directory-field follow-up keeps the directory target it depends on.

Recorded live (commit 92278e3, US session): "What is the delivery cost in Mali?"
was answered from sponsoring-014-mali, then "What's the minimum order amount?"
reached retrieval with target_country_names [] and include_global_documents
false, so Mali was lost and the turn was refused. The resolver inherited a
directory target for phone/hours/delivery/payment follow-ups but did not treat
a minimum-order request as a directory field.

Every test here is offline: AWS clients, embeddings, the OpenSearch client,
the planner/selector model and session writes are stubbed before use.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

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


def _no_live_calls(*_: object, **__: object):
    raise AssertionError("W4 tests must never make an AWS, embedding, OpenSearch or model call")


@pytest.fixture(autouse=True)
def _offline(monkeypatch) -> None:
    monkeypatch.setattr(retrieval_providers, "get_aws_clients", _no_live_calls)
    monkeypatch.setattr(opensearch_sections, "get_aws_clients", _no_live_calls)
    monkeypatch.setattr(opensearch_sections, "embed_text", _no_live_calls)
    monkeypatch.setattr(opensearch_sections, "_client", _no_live_calls)


def _history(*turns: str) -> str:
    lines = []
    for turn in turns:
        lines.extend([f"user: {turn}", "vera: An earlier answer."])
    return "\n".join(lines)


def _resolve(message: str, history: str) -> tuple[str, str]:
    orchestrator = AIOrchestrator()
    retrieval_query = orchestrator._build_retrieval_query(message, history, "cid")
    return retrieval_query, orchestrator._build_request_query(message, retrieval_query, history)


def _stub_planner(monkeypatch, scopes: str = '["locale_policy"]') -> None:
    runtime = MagicMock()
    runtime.converse.return_value = {
        "output": {"message": {"content": [{
            "text": '{"queries":["order terms"],"document_scopes":' + scopes
            + ',"intent":"knowledge","intent_confidence":0.99}'
        }]}}
    }
    monkeypatch.setattr(retrieval_providers.settings, "BEDROCK_QUERY_PLANNER_ENABLED", True)
    monkeypatch.setattr(retrieval_providers, "get_aws_clients", lambda: SimpleNamespace(bedrock_runtime=runtime))


# --- Fail-before: the Mali target survives a short directory-field follow-up ----------


@pytest.mark.parametrize(
    "follow_up",
    ["What's the minimum order amount?", "And the minimum order?", "How much is delivery?", "What payment methods?"],
)
def test_directory_field_follow_up_inherits_the_named_target(follow_up) -> None:
    retrieval, request = _resolve(follow_up, _history(MALI))
    assert retrieval == f"{MALI}\nFollow-up request: {follow_up}"
    assert request == retrieval


def test_resolved_minimum_order_follow_up_reaches_mali_directory_scope(monkeypatch) -> None:
    follow_up = "What's the minimum order amount?"
    retrieval, _ = _resolve(follow_up, _history(MALI))
    _stub_planner(monkeypatch)
    plan = retrieval_providers._planned_retrieval_plan(retrieval, "US", "en", "cid")
    assert plan.include_global_documents is True
    assert opensearch_sections._directory_target_country_names(retrieval, "US") == {"Mali"}


def test_minimum_order_target_persists_across_consecutive_field_changes() -> None:
    minimum, payment = "What's the minimum order amount?", "What payment methods?"
    assert _resolve(payment, _history(MALI, minimum))[0] == f"{MALI}\nFollow-up request: {payment}"


# --- Controls --------------------------------------------------------------------------


def test_new_substantive_topic_stops_minimum_order_inheritance() -> None:
    returns = "What is the return policy?"
    follow_up = "What's the minimum order amount?"
    assert _resolve(returns, _history(MALI))[0] == returns
    retrieval, request = _resolve(follow_up, _history(MALI, returns))
    assert retrieval == follow_up and request == follow_up


def test_fresh_session_minimum_order_follow_up_inherits_nothing() -> None:
    follow_up = "What's the minimum order amount?"
    assert _resolve(follow_up, "") == (follow_up, follow_up)


def test_explicit_new_country_replaces_the_target() -> None:
    question = "What's the minimum order amount in Germany?"
    assert _resolve(question, _history(MALI))[0] == question


def test_us_session_foreign_company_policy_is_still_refused_after_directory_turns() -> None:
    policy = "What is the company policy in Mali on returns?"
    retrieval, _ = _resolve(policy, _history(MALI, "What's the minimum order amount?"))
    documents = [
        RetrievedDocument(
            id=f"{code}:9.01", title="t", content="Returns policy.", source=f"s3://{code}", country=code,
            language="en", score=score, metadata={"access_scope": "country", "document_type": "policy", "status": "active"},
        )
        for code, score in (("ML", 0.95), ("US", 0.9))
    ]
    decision = approve_evidence(retrieval, RetrievalResult(documents=documents, citations=[], confidence=0.9), "US", "en")
    assert decision.approved is False
    assert decision.reason == "cross_market_policy_request"


def test_return_policy_question_is_not_routed_to_the_directory(monkeypatch) -> None:
    question = "What is the return policy?"
    assert _resolve(question, _history(MALI)) == (question, question)
    _stub_planner(monkeypatch)
    plan = retrieval_providers._planned_retrieval_plan(question, "NL", "en", "cid")
    assert plan.include_global_documents is False


def test_policy_word_follow_up_does_not_inherit() -> None:
    question = "What is the minimum order policy?"
    assert _resolve(question, _history(MALI))[0] == question


# --- The cache identity follows the resolved request -----------------------------------


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


def test_cache_identity_follows_the_resolved_minimum_order_request(monkeypatch) -> None:
    follow_up = "What's the minimum order amount?"
    mali = _run_session(monkeypatch, _history(MALI), follow_up)
    fresh = _run_session(monkeypatch, "", follow_up)
    assert "Mali" in mali["retrieval"] and mali["exact"] == mali["retrieval"]
    assert fresh["exact"] == fresh["retrieval"] == follow_up
    assert mali["exact_key"] != fresh["exact_key"]
