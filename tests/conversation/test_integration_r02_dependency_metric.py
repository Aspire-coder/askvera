"""R11 integration: R02 routing and the Lane E metric share one fallback builder. Mocked dependency behaviour.

Before integration there were two independent fallback implementations. Codex's
R02 routing sites built the outage copy inline and recorded no metric; Lane E's
`_dependency_unavailable_response` recorded DependencyUnavailable but could see
only raised exceptions. Both R02 sites now call the shared builder.

These tests drive the real `_route_or_approve_evidence` with the scenarios from
tests/unit/test_chat_orchestrator.py's R02 tests and check the metric boundary:
- exactly one DependencyUnavailable for each outage outcome, carrying the real
  availability value;
- none for a foreign company-policy scope refusal, and none for degraded
  retrieval that still has usable evidence.

Nothing here reaches OpenSearch, Bedrock or CloudWatch; the metric sink is
monkeypatched.
"""

from __future__ import annotations

import pytest

from app.governance.models import GovernanceAction, GovernanceDecision
from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.retrieval.models import RetrievalAvailability, RetrievalResult, RetrievedDocument
from app.validation.models import ValidationResult
from utils.validators import ChatRequest


class _Validator:
    def validate(self, *_: object, **__: object) -> ValidationResult:
        return ValidationResult()


class _Governance:
    def evaluate(self, *, text: str, **_: object) -> GovernanceDecision:
        return GovernanceDecision(allowed=True, action=GovernanceAction.ALLOW, provider="test")


@pytest.fixture()
def recorded(monkeypatch) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        chat_orchestrator, "record_dependency_unavailable", lambda component, availability: calls.append((component, availability))
    )
    monkeypatch.setattr(chat_orchestrator, "append_session_turn", lambda *_: None)
    return calls


def _route(body: ChatRequest, result: RetrievalResult):
    orchestrator = AIOrchestrator(validator=_Validator(), governance=_Governance())
    return orchestrator._route_or_approve_evidence(body.message, result, body.message, body, "r02-metric-cid")


def _us(message: str) -> ChatRequest:
    return ChatRequest(message=message, sessionId="session-1", country="US", language="en")


def _us_policy_doc(content: str) -> RetrievedDocument:
    return RetrievedDocument(
        id="us-policy", title="US policy", content=content, source="s3://approved/us-policy.pdf",
        country="US", language="en", score=0.9, metadata={"access_scope": "country"},
    )


def test_unavailable_retrieval_records_the_metric_once_with_its_availability(recorded) -> None:
    response, _, _ = _route(
        _us("What are manager qualifications?"),
        RetrievalResult(documents=[], citations=[], confidence=0.0, availability=RetrievalAvailability.UNAVAILABLE),
    )
    assert response.metadata["failure_layer"] == "dependency_unavailable"
    assert response.metadata["retrieval_availability"] == "unavailable"
    assert recorded == [("retrieval", "unavailable")]


def test_degraded_global_loss_after_scope_reapproval_records_the_metric_once(recorded) -> None:
    """R02's retained regression: US session, Mexico office, failed global channels."""
    local = _us_policy_doc("US policy contact information.")
    response, _, _ = _route(
        _us("What is the Mexico office phone?"),
        RetrievalResult(
            documents=[local], citations=[local.to_source()], confidence=0.9,
            metadata={"failed_search_channels": ["global_text", "global_vector"]},
            availability=RetrievalAvailability.DEGRADED,
        ),
    )
    assert response.metadata["failure_layer"] == "dependency_unavailable"
    assert response.metadata["retrieval_availability"] == "degraded"
    assert recorded == [("retrieval", "degraded")]


def test_foreign_policy_scope_refusal_is_not_a_dependency_event(recorded, monkeypatch) -> None:
    orchestrator_addendum = "_office_contact_addendum"
    monkeypatch.setattr(AIOrchestrator, orchestrator_addendum, lambda *_: "")
    local = _us_policy_doc("US manager qualifications.")
    response, _, decision = _route(
        _us("What does Mexico company policy say about manager qualifications?"),
        RetrievalResult(
            documents=[local], citations=[local.to_source()], confidence=0.9,
            metadata={"failed_search_channels": ["global_text"]},
            availability=RetrievalAvailability.DEGRADED,
        ),
    )
    assert decision is not None and decision.reason == "cross_market_policy_request"
    assert response.metadata["failure_layer"] == "evidence_gate"
    assert recorded == []


def test_degraded_retrieval_with_usable_evidence_is_not_a_dependency_event(recorded) -> None:
    document = RetrievedDocument(
        id="mexico-office", title="International office directory - Mexico", content="Mexico office phone details.",
        source="s3://approved/global-directory.pdf", country="GLOBAL", language="en", score=0.9,
        metadata={"access_scope": "global", "document_type": "office_directory"},
    )
    response, _, decision = _route(
        _us("What is the Mexico office phone?"),
        RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.9,
                        availability=RetrievalAvailability.DEGRADED),
    )
    assert response is None
    assert decision is not None and decision.approved
    assert recorded == []
