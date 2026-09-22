"""Mocked-dependency tests for the DependencyUnavailable metric wiring.

Drives `AIOrchestrator.handle_chat` with the orchestrator wiring integrated:
the coordinator applied docs/conversation-quality/phase2/patches/
laneE-dependency-wiring.patch. The three `test_metric_fires_once_for_*`
cases were strict xfails on the Lane E branch and pass here.

The negative tests (the metric must NOT fire for missing evidence, low
confidence, a ConfigurationError or a guardrail block) were trivially true
before the wiring existed. They are meaningful only now that the metric is
actually called.

Not covered here: Codex's R02 `RetrievalResult.availability` routing. It
lives in the Evidence-First V2 worktree and is combined at R11 integration,
where its two routing sites must call `_dependency_unavailable_response`
with a real availability value.
"""

from __future__ import annotations

import pytest
from botocore.exceptions import BotoCoreError

from app.governance.models import GovernanceAction, GovernanceDecision
from app.models.responses import ModelResponse
from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.retrieval.models import RetrievedDocument, RetrievalResult
from app.validation.models import ValidationResult
from config import settings
from services import session as session_module
from utils.exceptions import AwsServiceError, BedrockTimeoutError, ConfigurationError, RetrievalMissError
from utils.validators import ChatRequest


class _FakeGovernance:
    def evaluate(self, *, text: str, **_kwargs) -> GovernanceDecision:
        return GovernanceDecision(allowed=True, action=GovernanceAction.ALLOW, provider="test")


class _FakeValidator:
    def validate(self, *_args, **_kwargs) -> ValidationResult:
        return ValidationResult()


class _RecordedCalls(list):
    def __call__(self, component: str, availability: str) -> None:
        self.append((component, availability))


@pytest.fixture(autouse=True)
def _local_memory_and_wiring(monkeypatch):
    monkeypatch.setattr(settings, "CHAT_MEMORY_BACKEND", "memory")
    session_module._reset_memory_sessions()
    monkeypatch.setattr(chat_orchestrator, "validate_and_touch_session", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "has_valid_consent", lambda *_: True)
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_, **__: text)
    monkeypatch.setattr(chat_orchestrator, "get_session_history", lambda *_: "")
    monkeypatch.setattr(chat_orchestrator, "build_cache_key", lambda *_: "cache-key")
    monkeypatch.setattr(chat_orchestrator, "get_cache_value", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "set_cache_value", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "append_session_turn", lambda *_: None)
    monkeypatch.setattr(chat_orchestrator, "write_audit_event", lambda *_: None)
    yield
    session_module._reset_memory_sessions()


@pytest.fixture()
def recorded_calls(monkeypatch) -> _RecordedCalls:
    """Capture calls to record_dependency_unavailable as seen by the
    orchestrator module. `raising=False` so this fixture works identically
    whether or not the patch (which imports the name into chat_orchestrator's
    namespace) has been applied -- pre-patch, nothing ever calls the
    substitute, which is exactly the gap these tests pin."""
    calls = _RecordedCalls()
    monkeypatch.setattr(chat_orchestrator, "record_dependency_unavailable", calls, raising=False)
    return calls


def _handle(retriever, router, message: str, language: str = "en", country: str = "US"):
    orchestrator = AIOrchestrator(
        retriever=retriever, router=router, validator=_FakeValidator(), governance=_FakeGovernance()
    )
    body = ChatRequest(message=message, sessionId="s1", country=country, language=language)
    return orchestrator.handle_chat(body, "cid")


class _RetrieverRaisesBotoCoreError:
    def retrieve(self, *_args, **_kwargs):
        raise BotoCoreError()


class _RetrieverRaisesEmbeddingOutage:
    def retrieve(self, *_args, **_kwargs):
        raise AwsServiceError("Embedding generation failed.")


class _RetrieverEmpty:
    def retrieve(self, *_args, **_kwargs) -> RetrievalResult:
        return RetrievalResult(documents=[], citations=[], confidence=0.0, metadata={})


class _RetrieverWithEvidence:
    def retrieve(self, *_args, **_kwargs) -> RetrievalResult:
        document = RetrievedDocument(
            id="rm",
            title="Policy - Recognized Manager",
            content="A Forever Business Owner can become a Recognized Manager by meeting the policy requirements.",
            source="s3://approved/policy.pdf",
            country="US",
            language="en",
            score=0.9,
        )
        return RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.9)


class _RouterOk:
    def generate(self, *_args, **_kwargs) -> ModelResponse:
        return ModelResponse(text="answer text", citations=[], confidence=0.9, provider="test", model_name="test")


class _RouterRaisesBedrockTimeout:
    def generate(self, *_args, **_kwargs):
        raise BedrockTimeoutError("bedrock timed out")


class _RouterRaisesLowConfidence:
    def generate(self, *_args, **_kwargs):
        raise RetrievalMissError("no evidence")


class _RouterRaisesConfigurationError:
    def generate(self, *_args, **_kwargs):
        raise ConfigurationError("BEDROCK_MODEL_ID is not configured yet.")


def test_metric_fires_once_for_bedrock_timeout(recorded_calls):
    response = _handle(_RetrieverWithEvidence(), _RouterRaisesBedrockTimeout(), "How do I qualify as a Recognized Manager?")
    assert response.metadata.get("failure_layer") == "dependency_unavailable"
    assert recorded_calls == [("generation", "exception")]


def test_metric_fires_once_for_escaping_aws_service_error(recorded_calls):
    """The embedding path (services/embeddings.py) escapes retrieve() as
    AwsServiceError; component must be "embedding", not "retrieval"."""
    response = _handle(_RetrieverRaisesEmbeddingOutage(), _RouterOk(), "What is the minimum order for Kenya?")
    assert response.metadata.get("failure_layer") == "dependency_unavailable"
    assert recorded_calls == [("embedding", "exception")]


def test_metric_fires_once_for_escaping_boto_core_error(recorded_calls):
    response = _handle(_RetrieverRaisesBotoCoreError(), _RouterOk(), "What is the minimum order for Kenya?")
    assert response.metadata.get("failure_layer") == "dependency_unavailable"
    assert recorded_calls == [("retrieval", "exception")]


def test_metric_does_not_fire_for_missing_evidence(recorded_calls):
    response = _handle(_RetrieverEmpty(), _RouterOk(), "What is the FBO Support Fee?")
    assert response.metadata.get("failure_layer") == "evidence_gate"
    assert recorded_calls == []


def test_metric_does_not_fire_for_low_confidence(recorded_calls):
    response = _handle(_RetrieverWithEvidence(), _RouterRaisesLowConfidence(), "What is the FBO Support Fee?")
    assert response.metadata.get("failure_layer") in {"retrieval_miss", "low_confidence"}
    assert recorded_calls == []


def test_metric_does_not_fire_for_configuration_error(recorded_calls):
    """ConfigurationError must still propagate as an error, not become a
    dependency_unavailable chat answer, and must never touch this metric."""
    with pytest.raises(ConfigurationError):
        _handle(_RetrieverWithEvidence(), _RouterRaisesConfigurationError(), "How do I qualify as a Recognized Manager?")
    assert recorded_calls == []


def test_metric_does_not_fire_for_a_guardrail_block(recorded_calls):
    class _GovernanceBlocks:
        def evaluate(self, *, text: str, **_kwargs) -> GovernanceDecision:
            return GovernanceDecision(
                allowed=False,
                action=GovernanceAction.BLOCK,
                provider="test",
                metadata={"topic": "medical_claim"},
            )

    orchestrator = AIOrchestrator(
        retriever=_RetrieverEmpty(), router=_RouterOk(), validator=_FakeValidator(), governance=_GovernanceBlocks()
    )
    body = ChatRequest(message="Will this cure my illness?", sessionId="s1", country="US", language="en")
    response = orchestrator.handle_chat(body, "cid")
    assert response.metadata.get("failure_layer") != "dependency_unavailable"
    assert recorded_calls == []


# Coordinator, 2026-09-18 (CX, approval 6 option B): the answer now follows the
# language the message is written in, so each case writes its question in the
# widget's language. The English-message/French-widget case is asserted
# explicitly below instead of being implied here.
@pytest.mark.parametrize(
    "language,message,expected_phrase",
    [
        ("en", "How do I qualify as a Recognized Manager?", "technical hiccup"),
        ("fr", "Comment est-ce que je peux devenir Recognized Manager ?", "difficulté technique"),
        ("es", "¿Cómo puedo calificar como Recognized Manager?", "problema técnico"),
    ],
)
def test_dependency_copy_is_localized_and_never_the_missing_evidence_text(
    language, message, expected_phrase, recorded_calls
):
    response = _handle(_RetrieverWithEvidence(), _RouterRaisesBedrockTimeout(), message, language=language)
    assert response.metadata.get("failure_layer") == "dependency_unavailable"
    assert expected_phrase in response.answer.lower()
    assert "do not contain enough information" not in response.answer
    assert "ne contiennent pas suffisamment d'informations" not in response.answer.lower()


def test_dependency_copy_follows_the_message_language_not_the_widget(recorded_calls):
    # Approval 6 option B: an English question typed with the widget set to
    # French gets the English dependency copy; only presentation switches.
    response = _handle(
        _RetrieverWithEvidence(), _RouterRaisesBedrockTimeout(),
        "How do I qualify as a Recognized Manager in my country?", language="fr",
    )
    assert response.metadata.get("failure_layer") == "dependency_unavailable"
    assert "technical hiccup" in response.answer.lower()
    assert response.metadata["answer_language"] == {
        "selected": "fr", "answer": "en", "reason": response.metadata["answer_language"]["reason"],
    }
