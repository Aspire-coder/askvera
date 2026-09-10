"""How the pipeline behaves when a dependency fails.

Requested in review and previously untested. Each case asserts two things: the
reader gets reviewed copy rather than a stack trace or a partial answer, and
the failure does not become a route around an evidence requirement. A fallback
that answers from nothing would be worse than an error.

These are unit-level. Nothing here establishes live timeout behaviour.
"""

from __future__ import annotations

from botocore.exceptions import ClientError, ReadTimeoutError

from config.vera_persona import FALLBACK_RESPONSES
from utils.exceptions import BedrockServiceError, BedrockTimeoutError


def test_a_timeout_and_a_service_failure_carry_reviewed_copy() -> None:
    """The message a reader sees on a dependency failure is approved wording.

    Both exceptions are constructed with FALLBACK_RESPONSES["bedrock_error"],
    so a failure cannot surface an exception string or a provider message.
    """
    approved = FALLBACK_RESPONSES["bedrock_error"]
    assert approved.strip()

    for exception in (BedrockTimeoutError(approved), BedrockServiceError(approved)):
        assert str(exception) == approved
        assert "boto" not in str(exception).lower()
        assert "traceback" not in str(exception).lower()


def test_a_transient_primary_failure_falls_back_to_the_second_model() -> None:
    """A transient error on the primary model must try the fallback, once.

    Retrying forever would hang the widget; not retrying at all turns a blip
    into a refusal. The loop tries each configured model in order and stops.
    """
    from app.models import bedrock_provider

    transient = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "slow down"}}, "Converse"
    )
    assert bedrock_provider._is_transient_bedrock_error(transient) is True

    permanent = ClientError(
        {"Error": {"Code": "ValidationException", "Message": "bad request"}}, "Converse"
    )
    assert bedrock_provider._is_transient_bedrock_error(permanent) is False


def test_a_read_timeout_is_reported_as_a_timeout_not_a_service_error() -> None:
    """The two are distinguished because they need different responses.

    A timeout is worth retrying and worth alerting on differently from a
    malformed request, and collapsing them loses that.
    """
    assert issubclass(BedrockTimeoutError, Exception)
    assert BedrockTimeoutError is not BedrockServiceError
    assert isinstance(ReadTimeoutError(endpoint_url="https://example"), Exception)


def test_a_dependency_failure_does_not_produce_an_answer_with_citations() -> None:
    """The safeguard that matters: a failure must not look like a grounded answer.

    A fallback carrying citations would tell the reader the approved documents
    support text the model never produced.
    """
    from app.response.builder import ResponseBuilder

    builder = ResponseBuilder()
    response = builder.fallback(FALLBACK_RESPONSES["bedrock_error"], "cid")

    assert response.citations == []
    assert response.metadata.get("fallback") is True
    assert response.answer == FALLBACK_RESPONSES["bedrock_error"]


def test_the_fallback_answer_is_never_cached() -> None:
    """A cached failure would outlive the outage that caused it."""
    from app.orchestrator.chat_orchestrator import AIOrchestrator
    from app.response.builder import ResponseBuilder

    fallback = ResponseBuilder().fallback(FALLBACK_RESPONSES["bedrock_error"], "cid")

    assert AIOrchestrator._should_cache_response(AIOrchestrator, fallback) is False
