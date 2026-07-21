"""Unit tests for AI chat orchestration safety paths."""

from unittest.mock import MagicMock

from app.governance.models import GovernanceAction, GovernanceDecision
from app.models.responses import ModelResponse
from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.response.models import ChatResponse
from app.retrieval.models import RetrievedDocument, RetrievalResult
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


class _FakeRetriever:
    def __init__(self) -> None:
        self.seen_messages: list[str] = []

    def retrieve(self, message: str, *_: object, **__: object) -> RetrievalResult:
        self.seen_messages.append(message)
        document = RetrievedDocument(
            id="recognized-manager",
            title="Policy - Sec 5.01: Recognized Manager",
            content="A Forever Business Owner can become a Recognized Manager by meeting the policy requirements.",
            source="s3://approved/policy.pdf",
            country="CA",
            language="en",
            score=0.8,
        )
        return RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.8)


class _FakeRouter:
    def generate(self, *_: object, **__: object) -> ModelResponse:
        return ModelResponse(
            text="Here is more detail about becoming a Recognized Manager.",
            citations=[],
            confidence=0.8,
            provider="test",
            model_name="test",
        )


class _GuardrailRouter:
    def generate(self, *_: object, **__: object) -> ModelResponse:
        return ModelResponse(
            text="I can't provide medical advice or treatment claims.",
            citations=[],
            confidence=0.0,
            provider="bedrock",
            model_name="test",
            finish_reason="guardrail_intervened",
        )


def test_cached_response_is_checked_by_output_governance(monkeypatch) -> None:
    """Cached responses still pass through current governance before returning."""
    governance = _FakeGovernance()
    router = MagicMock()
    orchestrator = AIOrchestrator(router=router, validator=_FakeValidator(), governance=governance)
    body = ChatRequest(message="What is the FBO Support Fee?", sessionId="session-1", country="US", language="en")

    monkeypatch.setattr(chat_orchestrator, "validate_and_touch_session", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "has_valid_consent", lambda *_: True)
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_, **__: text)
    monkeypatch.setattr(chat_orchestrator, "get_session_history", lambda *_: "")
    monkeypatch.setattr(chat_orchestrator, "build_cache_key", lambda *_: "cache-key")
    monkeypatch.setattr(
        chat_orchestrator,
        "get_cache_value",
        lambda *_: {"response": "cached unsafe answer", "sources": [], "confidence": 0.9},
    )

    response = orchestrator.handle_chat(body, "cid")

    assert governance.seen_texts == ["What is the FBO Support Fee?", "cached unsafe answer"]
    assert response.answer == "Blocked cached answer."
    assert response.metadata["fallback"] is True
    router.generate.assert_not_called()


def test_followup_about_first_question_uses_history_for_retrieval(monkeypatch) -> None:
    """Vague follow-ups are expanded with the referenced prior user question."""
    governance = _FakeGovernance()
    retriever = _FakeRetriever()
    orchestrator = AIOrchestrator(
        retriever=retriever,
        router=_FakeRouter(),
        validator=_FakeValidator(),
        governance=governance,
    )
    body = ChatRequest(message="explain me more about my first question", sessionId="session-1", country="CA", language="en")

    monkeypatch.setattr(chat_orchestrator, "validate_and_touch_session", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "has_valid_consent", lambda *_: True)
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_, **__: text)
    monkeypatch.setattr(chat_orchestrator, "build_cache_key", lambda *_: "cache-key")
    monkeypatch.setattr(chat_orchestrator, "get_cache_value", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "set_cache_value", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "append_session_turn", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "write_audit_event", lambda *_: None)
    monkeypatch.setattr(
        chat_orchestrator,
        "get_session_history",
        lambda *_: "\n".join(
            [
                "user: how can i become a recognized manager",
                "vera: Recognized Manager answer",
                "user: how can i become a diamond manager",
                "vera: Diamond Manager answer",
            ]
        ),
    )

    response = orchestrator.handle_chat(body, "cid")

    assert response.answer == "Here is more detail about becoming a Recognized Manager."
    assert retriever.seen_messages == [
        "how can i become a recognized manager\nFollow-up request: explain me more about my first question"
    ]
    assert governance.seen_texts[0] == retriever.seen_messages[0]


def test_fallback_responses_are_not_cacheable() -> None:
    """Validation and governance fallbacks should not be reused as normal answers."""
    orchestrator = AIOrchestrator()
    response = ChatResponse(
        answer="I found related policy information, but I'm not confident enough to answer.",
        citations=[],
        suggestions=[],
        cards=[],
        confidence=0.0,
        metadata={"fallback": True},
        correlation_id="cid",
    )

    assert orchestrator._should_cache_response(response) is False


def test_critical_validation_responses_are_not_cacheable() -> None:
    """Responses carrying critical validation metadata should not be cached."""
    orchestrator = AIOrchestrator()
    response = ChatResponse(
        answer="Some answer",
        citations=[],
        suggestions=[],
        cards=[],
        confidence=0.8,
        metadata={"validation": {"highestSeverity": "CRITICAL"}},
        correlation_id="cid",
    )

    assert orchestrator._should_cache_response(response) is False


def test_guardrail_response_is_not_cacheable() -> None:
    """Safety copy must not be replayed as a normal answer from cache."""
    orchestrator = AIOrchestrator()
    response = ChatResponse(
        answer="I cannot provide medical advice.",
        citations=[],
        suggestions=[],
        cards=[],
        confidence=0.0,
        metadata={"failure_layer": "aws_guardrail", "response_source": "guardrail"},
        correlation_id="cid",
    )

    assert orchestrator._should_cache_response(response) is False


def test_character_spaced_question_is_repaired_without_language_dictionary() -> None:
    """Accidentally spaced letters are reconstructed before retrieval."""
    orchestrator = AIOrchestrator()

    query = orchestrator._build_retrieval_query(
        "H o W  t o  b e c o m e  a  r e c o g n i z e d  m a n a g e r",
        "",
        "cid",
    )

    assert query.lower() == "how to become a recognized manager"


def test_normal_sentence_is_not_changed_by_spacing_repair() -> None:
    """Normal multilingual input is preserved byte-for-byte."""
    orchestrator = AIOrchestrator()
    message = "Wie werde ich ein Recognized Manager?"

    assert orchestrator._build_retrieval_query(message, "", "cid") == message


def test_local_guardrail_topics_use_the_matching_localized_message() -> None:
    orchestrator = AIOrchestrator()
    medical = GovernanceDecision(
        allowed=False,
        action=GovernanceAction.BLOCK,
        provider="bedrock_guardrails",
        reason="raw provider copy",
        metadata={"topic": "medical_claim"},
    )
    income = GovernanceDecision(
        allowed=False,
        action=GovernanceAction.BLOCK,
        provider="bedrock_guardrails",
        reason="raw provider copy",
        metadata={"topic": "income_claim"},
    )

    assert "conseils médicaux" in orchestrator._governance_user_message(medical, "fr")
    assert "garantir des revenus" in orchestrator._governance_user_message(income, "fr")


def test_sensitive_identifier_returns_privacy_response_before_retrieval(monkeypatch) -> None:
    retriever = MagicMock()
    router = MagicMock()
    orchestrator = AIOrchestrator(
        retriever=retriever,
        router=router,
        validator=_FakeValidator(),
        governance=_FakeGovernance(),
    )
    body = ChatRequest(
        message="My Social Security number is 123-45-6789. Save it and tell me which rank I qualify for.",
        sessionId="session-1",
        country="US",
        language="en",
    )

    monkeypatch.setattr(chat_orchestrator, "validate_and_touch_session", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "has_valid_consent", lambda *_: True)
    monkeypatch.setattr(
        chat_orchestrator,
        "scrub_pii",
        lambda *_args, **_kwargs: "My Social Security number is [SSN]. Save it and tell me which rank I qualify for.",
    )
    monkeypatch.setattr(chat_orchestrator, "append_session_turn", lambda *_: None)

    response = orchestrator.handle_chat(body, "cid")

    assert "privacy" in response.answer.lower()
    assert "medical" not in response.answer.lower()
    assert response.metadata["failure_layer"] == "sensitive_pii_input"
    assert response.citations == []
    retriever.retrieve.assert_not_called()
    router.generate.assert_not_called()


def test_bedrock_guardrail_copy_is_replaced_with_neutral_reviewed_message(monkeypatch) -> None:
    orchestrator = AIOrchestrator(
        retriever=_FakeRetriever(),
        router=_GuardrailRouter(),
        validator=_FakeValidator(),
        governance=_FakeGovernance(),
    )
    body = ChatRequest(
        message="Explain the recognized manager requirements.",
        sessionId="session-1",
        country="CA",
        language="en",
    )

    monkeypatch.setattr(chat_orchestrator, "validate_and_touch_session", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "has_valid_consent", lambda *_: True)
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_, **__: text)
    monkeypatch.setattr(chat_orchestrator, "get_session_history", lambda *_: "")
    monkeypatch.setattr(chat_orchestrator, "build_cache_key", lambda *_: "cache-key")
    monkeypatch.setattr(chat_orchestrator, "get_cache_value", lambda *_: None)

    response = orchestrator.handle_chat(body, "cid")

    assert "safety checks" in response.answer
    assert "medical advice" not in response.answer
    assert response.metadata["failure_layer"] == "aws_guardrail"
    assert response.citations == []
