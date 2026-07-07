"""Unit tests for AI chat orchestration safety paths."""

from unittest.mock import MagicMock

from app.governance.models import GovernanceAction, GovernanceDecision
from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.validation.models import ValidationResult
from utils.validators import ChatRequest


class _FakeGovernance:
    def __init__(self) -> None:
        self.seen_texts: list[str] = []

    def evaluate(self, *, text: str, **_: object) -> GovernanceDecision:
        self.seen_texts.append(text)
        if text == "cached unsafe answer":
            return GovernanceDecision(
                allowed=False,
                action=GovernanceAction.BLOCK,
                provider="test",
                reason="Blocked cached answer.",
            )
        return GovernanceDecision(allowed=True, action=GovernanceAction.ALLOW, provider="test")


class _FakeValidator:
    def validate(self, *_: object, **__: object) -> ValidationResult:
        return ValidationResult()


def test_cached_response_is_checked_by_output_governance(monkeypatch) -> None:
    """Cached responses still pass through current governance before returning."""
    governance = _FakeGovernance()
    router = MagicMock()
    orchestrator = AIOrchestrator(router=router, validator=_FakeValidator(), governance=governance)
    body = ChatRequest(message="hello", sessionId="session-1", country="US", language="en")

    monkeypatch.setattr(chat_orchestrator, "validate_and_touch_session", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "has_valid_consent", lambda *_: True)
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_: text)
    monkeypatch.setattr(chat_orchestrator, "build_cache_key", lambda *_: "cache-key")
    monkeypatch.setattr(
        chat_orchestrator,
        "get_cache_value",
        lambda *_: {"response": "cached unsafe answer", "sources": [], "confidence": 0.9},
    )

    response = orchestrator.handle_chat(body, "cid")

    assert governance.seen_texts == ["hello", "cached unsafe answer"]
    assert response.answer == "Blocked cached answer."
    assert response.metadata["fallback"] is True
    router.generate.assert_not_called()
