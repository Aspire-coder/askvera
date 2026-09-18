"""Mocked-dependency tests for the DependencyUnavailable metric wiring.

SOME TESTS BELOW REQUIRE laneE-dependency-wiring.patch
---------------------------------------------------------
This file exercises `AIOrchestrator.handle_chat` on THIS branch, where
`app/orchestrator/chat_orchestrator.py` has NOT been edited (Lane E may not
write that file; see docs/conversation-quality/TASK_BOARD.md Phase 2 file
ownership). The three `test_metric_fires_once_for_*` cases assert that
`record_dependency_unavailable` was actually called with a specific
(component, availability) pair -- that call does not exist anywhere on this
branch, so those three are marked `xfail(strict=True, reason="needs
laneE-dependency-wiring.patch")` and are expected to XFAIL here. Once the
coordinator applies `docs/conversation-quality/phase2/patches/
laneE-dependency-wiring.patch` (which wires that call into both existing
dependency catches), those three flip to passing and the `xfail` marker must
come off.

SCOPE NOTE: an earlier version of this file also had a fourth gated test for
a `metadata["provider_unavailable"]` result flag. That design is withdrawn
in favor of Codex's accepted R02 contract (`RetrievalResult.availability`),
which lives in Codex's worktree, not this project's base, and is routed by
Codex's own orchestrator hook at integration -- not by anything in this
patch or this test file. See docs/conversation-quality/codex-requests/
C5-retrieval-outage-masked-as-no-evidence.md.

Every other test in this file asserts the metric's *negative* space (must
NOT fire for missing evidence, low confidence, a ConfigurationError, or a
guardrail block) and the *existing, already-merged* localized dependency
copy for the generate()-path Bedrock catch. Those hold true on this branch
today -- the metric simply never fires at all yet, so "does not fire" is
trivially satisfied -- and must keep holding true after the patch, so they
are deliberately NOT marked xfail: a regression in either direction should
fail this file both before and after integration.

Proof the three gated tests flip once the patch is applied: run, from a
scratch copy of this worktree with the patch applied,

    git apply docs/conversation-quality/phase2/patches/laneE-dependency-wiring.patch
    <PYTHON> -m pytest tests/conversation/test_dependency_orchestrator_wiring.py \
        -p no:cacheprovider --basetemp <scratch-basetemp> -rA

and confirm the three `test_metric_fires_once_for_*` cases show XPASS
(strict, so an unexpected pass fails the run unless the `xfail` marker is
removed there) while every other test in the file still shows PASSED. See
the Lane E handoff for the exact commands and their captured output.

No live model or AWS call is made anywhere in this file: retriever, router,
governance, validator and session plumbing are all fakes, exactly like
tests/conversation/test_intent_dependency_failures_are_distinct.py, which
this file complements (that file pins the *user-facing wording*; this file
pins the *metric*).
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

XFAIL = pytest.mark.xfail(strict=True, reason="needs laneE-dependency-wiring.patch")


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


@XFAIL
def test_metric_fires_once_for_bedrock_timeout(recorded_calls):
    response = _handle(_RetrieverWithEvidence(), _RouterRaisesBedrockTimeout(), "How do I qualify as a Recognized Manager?")
    assert response.metadata.get("failure_layer") == "dependency_unavailable"
    assert recorded_calls == [("generation", "exception")]


@XFAIL
def test_metric_fires_once_for_escaping_aws_service_error(recorded_calls):
    """The embedding path (services/embeddings.py) escapes retrieve() as
    AwsServiceError; component must be "embedding", not "retrieval"."""
    response = _handle(_RetrieverRaisesEmbeddingOutage(), _RouterOk(), "What is the minimum order for Kenya?")
    assert response.metadata.get("failure_layer") == "dependency_unavailable"
    assert recorded_calls == [("embedding", "exception")]


@XFAIL
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


@pytest.mark.parametrize(
    "language,expected_phrase",
    [
        ("en", "technical hiccup"),
        ("fr", "difficulté technique"),
        ("es", "problema técnico"),
    ],
)
def test_dependency_copy_is_localized_and_never_the_missing_evidence_text(language, expected_phrase, recorded_calls):
    response = _handle(
        _RetrieverWithEvidence(), _RouterRaisesBedrockTimeout(), "How do I qualify as a Recognized Manager?",
        language=language,
    )
    assert response.metadata.get("failure_layer") == "dependency_unavailable"
    assert expected_phrase in response.answer.lower()
    assert "do not contain enough information" not in response.answer
    assert "ne contiennent pas suffisamment d'informations" not in response.answer.lower()
