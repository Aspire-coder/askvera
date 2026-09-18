"""C5 (re-check, end-to-end): a dependency failure (retrieval backend down,
model provider down) must get its OWN distinct, honest wording - never the
same "documents don't contain enough information" denial used for genuinely
missing evidence, and never no wording at all.

Reproduced end-to-end (2026-09-18) by calling the real
AIOrchestrator.handle_chat with the offline harness pattern (fake retriever/
router/validator/governance/session, no live model or AWS calls):

(a) self.retriever.retrieve(...) in _handle_scrubbed_chat
    (app/orchestrator/chat_orchestrator.py, ~line 1049) was completely
    unguarded. A retrieval-backend outage (BotoCoreError/ClientError/
    ConnectionError/TimeoutError/OSError) raised straight out of
    handle_chat with NO ChatResponse at all - not even the wrong wording,
    literally nothing delivered, and the turn was never persisted to
    session history (append_session_turn runs later in _handle_chat, after
    the exception already propagated).

(b) self.model_router.generate(...) (~line 1078) only caught
    LowConfidenceError. BedrockTimeoutError/BedrockServiceError (raised by
    app/models/bedrock_provider.py when Bedrock itself times out or errors -
    both AskVeraError subclasses, NEITHER a LowConfidenceError) propagated
    past this call, past handle_chat, and were only ever caught - if the
    caller happened to be api/routes.py - by its bare `except AskVeraError`,
    which returns a `success: false` HTTP error ENVELOPE (a completely
    different response shape than every other outcome in this file), never
    runs response_builder or output validation, and carries no
    metadata.failure_layer at all.

By contrast, missing evidence (c) and a policy-country restriction (d) both
already return an ordinary ChatResponse with distinct wording and
failure_layer "evidence_gate" (see the same test file's assertions on (c)/
(d) for that baseline).

The orchestrator is coordinator-only, so the fix is delivered as a unified
diff at docs/conversation-quality/patches/laneC-failure-wording.patch (not
applied to app/orchestrator/chat_orchestrator.py in this worktree). It:
- wraps the retrieve() call and returns the reviewed "bedrock_error" copy
  with failure_layer="dependency_unavailable" on a dependency exception;
- adds a second `except AskVeraError` clause after `except LowConfidenceError`
  around model_router.generate(), routing to the same fallback path and
  failure_layer.

These tests are written against the CURRENT (unpatched) orchestrator and
therefore currently FAIL, pinning the live defect; they are expected to pass
once the coordinator applies the patch. tests (c)-(f) alongside them pass
today and are included so the full six-situation picture is visible in one
file, per the coordinator's request to re-check C5 end-to-end.
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
from utils.exceptions import BedrockTimeoutError, RetrievalMissError
from utils.validators import ChatRequest


class _FakeGovernance:
    def evaluate(self, *, text: str, **_kwargs) -> GovernanceDecision:
        return GovernanceDecision(allowed=True, action=GovernanceAction.ALLOW, provider="test")


class _FakeValidator:
    def validate(self, *_args, **_kwargs) -> ValidationResult:
        return ValidationResult()


class _RetrieverRaisesConnectionError:
    def retrieve(self, *_args, **_kwargs):
        raise BotoCoreError()


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


def _handle(retriever, router, message: str, country: str = "US") -> "chat_orchestrator.ChatResponse":
    orchestrator = AIOrchestrator(
        retriever=retriever, router=router, validator=_FakeValidator(), governance=_FakeGovernance()
    )
    body = ChatRequest(message=message, sessionId="s1", country=country, language="en")
    return orchestrator.handle_chat(body, "cid")


def test_a_retrieval_backend_outage_gets_a_dependency_answer_not_a_crash() -> None:
    response = _handle(
        _RetrieverRaisesConnectionError(), _RouterOk(), "What is the minimum order for Kenya?"
    )
    assert response.metadata.get("failure_layer") == "dependency_unavailable"
    assert "technical hiccup" in response.answer.lower()
    # Must never claim the information is unavailable - it's the DEPENDENCY
    # that's unavailable, not the documents.
    assert "do not contain enough information" not in response.answer


def test_b_model_provider_outage_gets_a_dependency_answer_not_an_error_envelope() -> None:
    response = _handle(
        _RetrieverWithEvidence(), _RouterRaisesBedrockTimeout(), "How do I qualify as a Recognized Manager?"
    )
    assert response.metadata.get("failure_layer") == "dependency_unavailable"
    assert "technical hiccup" in response.answer.lower()


def test_c_missing_evidence_gets_its_own_wording_today() -> None:
    """Baseline (already correct): genuinely missing evidence never claims a
    technical problem, and is distinct from (a)/(b)."""
    response = _handle(_RetrieverEmpty(), _RouterOk(), "What is the FBO Support Fee?")
    assert response.metadata.get("failure_layer") == "evidence_gate"
    assert "technical hiccup" not in response.answer.lower()
    assert "do not contain enough information" in response.answer


def test_c_via_low_confidence_router_error_also_distinct_from_dependency_failure() -> None:
    """A model-side LowConfidenceError (the model ran, but had nothing to
    ground an answer in) must keep its own wording too, distinct from a real
    dependency outage."""
    response = _handle(_RetrieverWithEvidence(), _RouterRaisesLowConfidence(), "What is the FBO Support Fee?")
    assert response.metadata.get("failure_layer") in {"retrieval_miss", "low_confidence"}
    assert "technical hiccup" not in response.answer.lower()


def test_d_policy_country_restriction_is_distinct_from_missing_evidence_and_dependency_failure() -> None:
    class _RetrieverForeignPolicy:
        def retrieve(self, *_args, **_kwargs) -> RetrievalResult:
            document = RetrievedDocument(
                id="se-policy",
                title="Sweden Policy",
                content="Sweden-only policy content.",
                source="s3://approved/se.pdf",
                country="SE",
                language="en",
                score=0.9,
            )
            return RetrievalResult(documents=[document], citations=[document.to_source()], confidence=0.9)

    response = _handle(
        _RetrieverForeignPolicy(), _RouterOk(), "What is the company policy in Sweden on returns?", country="US"
    )
    assert "another market" in response.answer
    assert "technical hiccup" not in response.answer.lower()
    assert "do not contain enough information" not in response.answer


def test_e_outside_scope_wording_is_distinct() -> None:
    class _RetrieverOffTopic:
        def retrieve(self, *_args, **_kwargs) -> RetrievalResult:
            return RetrievalResult(documents=[], citations=[], confidence=0.0, metadata={"conversation_intent": "off_topic"})

    response = _handle(_RetrieverOffTopic(), _RouterOk(), "Can you help me place a bet on the game tonight?")
    assert "can't help with that question" in response.answer
    assert "technical hiccup" not in response.answer.lower()


def test_f_ambiguous_country_gets_a_clarification_not_a_refusal() -> None:
    response = _handle(_RetrieverEmpty(), _RouterOk(), "What is the minimum order in Swedn?")
    assert "did you mean" in response.answer.lower()
    assert "technical hiccup" not in response.answer.lower()


class _RouterRaisesConfigurationError:
    def generate(self, *_args, **_kwargs):
        from utils.exceptions import ConfigurationError

        raise ConfigurationError("BEDROCK_MODEL_ID is not configured yet.")


def test_configuration_error_is_not_disguised_as_a_transient_hiccup() -> None:
    """Negative control for the coordinator's narrowing of the patch.

    A ConfigurationError is a deploy defect, not a dependency outage. Telling
    the user "try again in a moment" would be false and would hide the defect
    from the request error-rate alarm, so it must still propagate to the
    route's error envelope rather than become a normal chat answer.
    """
    from utils.exceptions import ConfigurationError

    with pytest.raises(ConfigurationError):
        _handle(_RetrieverWithEvidence(), _RouterRaisesConfigurationError(), "How do I qualify as a Recognized Manager?")
