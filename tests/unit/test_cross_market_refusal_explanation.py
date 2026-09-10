from types import SimpleNamespace

from app.evidence import approve_evidence
from app.orchestrator.chat_orchestrator import AIOrchestrator, CROSS_MARKET_POLICY_SCOPE_RESPONSE
from app.retrieval.models import RetrievalResult


def _orchestrator_stub():
    return SimpleNamespace(
        _insufficient_evidence_message=lambda language, message="": (
            AIOrchestrator._insufficient_evidence_message(None, language, message)
        )
    )


def test_foreign_policy_is_refused_with_scope_explanation_in_english() -> None:
    decision = approve_evidence(
        "What is the company policy on returns in Belgium?",
        RetrievalResult(documents=[], citations=[], confidence=0.0, metadata={}),
        country="US",
        language="en",
    )

    assert decision.approved is False
    assert decision.reason == "cross_market_policy_request"
    assert AIOrchestrator._cross_market_scope_message(_orchestrator_stub(), "en") == (
        CROSS_MARKET_POLICY_SCOPE_RESPONSE
    )


def test_non_english_scope_refusal_keeps_existing_localized_fallback() -> None:
    message = AIOrchestrator._cross_market_scope_message(_orchestrator_stub(), "fr", "Belgium")

    assert "only available to readers" not in message
    assert message == AIOrchestrator._insufficient_evidence_message(None, "fr", "Belgium")
