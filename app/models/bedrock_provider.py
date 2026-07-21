"""Bedrock Claude model provider."""

from threading import Lock
from time import monotonic, perf_counter

from botocore.exceptions import BotoCoreError, ClientError, ReadTimeoutError

from app.prompts import PromptPackage
from app.response.normalizer import response_normalizer
from app.retrieval import RetrievalResult, score_summary, source_log_summary
from config import settings
from config.vera_persona import FALLBACK_RESPONSES
from services.aws_clients import get_aws_clients
from utils.exceptions import (
    BedrockServiceError,
    BedrockTimeoutError,
    ConfigurationError,
    LowConfidenceThresholdError,
    RetrievalMissError,
)
from utils.logging import get_logger

from .responses import ModelResponse

LOGGER = get_logger("app.models.bedrock")

_TRANSIENT_BEDROCK_ERROR_CODES = {
    "InternalServerException",
    "ModelNotReadyException",
    "ModelTimeoutException",
    "ServiceQuotaExceededException",
    "ServiceUnavailableException",
    "ThrottlingException",
}
_CIRCUIT_LOCK = Lock()
_PRIMARY_FAILURES = 0
_PRIMARY_OPEN_UNTIL = 0.0


def _reset_circuit_breaker() -> None:
    """Reset process-local model health state for tests and recovery checks."""
    global _PRIMARY_FAILURES, _PRIMARY_OPEN_UNTIL
    with _CIRCUIT_LOCK:
        _PRIMARY_FAILURES = 0
        _PRIMARY_OPEN_UNTIL = 0.0


def _primary_circuit_open() -> bool:
    with _CIRCUIT_LOCK:
        return monotonic() < _PRIMARY_OPEN_UNTIL


def _record_primary_success() -> None:
    _reset_circuit_breaker()


def _record_primary_failure() -> None:
    global _PRIMARY_FAILURES, _PRIMARY_OPEN_UNTIL
    threshold = max(1, int(settings.BEDROCK_CIRCUIT_BREAKER_FAILURE_THRESHOLD))
    with _CIRCUIT_LOCK:
        _PRIMARY_FAILURES += 1
        if _PRIMARY_FAILURES >= threshold:
            _PRIMARY_OPEN_UNTIL = monotonic() + max(1, int(settings.BEDROCK_CIRCUIT_BREAKER_RESET_SECONDS))


def _is_transient_bedrock_error(exc: BaseException) -> bool:
    if isinstance(exc, (ReadTimeoutError, BotoCoreError)):
        return True
    if not isinstance(exc, ClientError):
        return False
    code = str(exc.response.get("Error", {}).get("Code", ""))
    return code in _TRANSIENT_BEDROCK_ERROR_CODES or int(exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0) or 0) >= 500


def _has_adequate_evidence(summary: dict[str, object]) -> bool:
    """Return true when retrieval found enough evidence to attempt generation."""
    top_score = summary.get("top_score")
    source_count = summary.get("source_count")
    try:
        normalized_top_score = float(top_score) if top_score is not None else 0.0
        normalized_source_count = int(source_count) if source_count is not None else 0
    except (TypeError, ValueError):
        return False
    return (
        normalized_source_count >= settings.BEDROCK_CONFIDENCE_EVIDENCE_MIN_SOURCES
        and normalized_top_score >= settings.BEDROCK_CONFIDENCE_EVIDENCE_TOP_SCORE
    )


class BedrockClaudeProvider:
    """Generate answers with Claude through Bedrock Runtime."""

    name = "claude"

    def generate(self, prompt: PromptPackage, retrieval_result: RetrievalResult, correlation_id: str) -> ModelResponse:
        """Convert a prompt package into a Bedrock Converse request."""
        self._validate_configuration()
        sources = retrieval_result.sources
        confidence = retrieval_result.confidence
        summary = score_summary(sources)
        if not sources:
            LOGGER.warning(
                "model_no_sources",
                correlation_id=correlation_id,
                country=prompt.country,
                language=prompt.language,
                provider=self.name,
                confidence=confidence,
                failure_layer="retrieval_miss",
            )
            raise RetrievalMissError(FALLBACK_RESPONSES["low_confidence"])

        strong_local_match = bool(retrieval_result.metadata.get("strong_local_match"))
        adequate_evidence = _has_adequate_evidence(summary)
        if confidence < settings.BEDROCK_MIN_CONFIDENCE and not strong_local_match and not adequate_evidence:
            LOGGER.warning(
                "model_low_confidence_blocked",
                correlation_id=correlation_id,
                country=prompt.country,
                language=prompt.language,
                provider=self.name,
                confidence=confidence,
                failure_layer="low_confidence",
                **summary,
                sources=source_log_summary(sources),
            )
            raise LowConfidenceThresholdError(FALLBACK_RESPONSES["low_confidence"])
        if confidence < settings.BEDROCK_MIN_CONFIDENCE and adequate_evidence:
            LOGGER.warning(
                "model_low_confidence_allowed_by_evidence",
                correlation_id=correlation_id,
                country=prompt.country,
                language=prompt.language,
                provider=self.name,
                confidence=confidence,
                **summary,
                sources=source_log_summary(sources),
            )
        if confidence < settings.BEDROCK_MIN_CONFIDENCE and strong_local_match:
            LOGGER.warning(
                "model_low_confidence_allowed_by_local_match",
                correlation_id=correlation_id,
                country=prompt.country,
                language=prompt.language,
                provider=self.name,
                confidence=confidence,
                max_local_relevance=retrieval_result.metadata.get("max_local_relevance"),
                **summary,
                sources=source_log_summary(sources),
            )

        params = {
            "system": [{"text": prompt.system_prompt}],
            "messages": [{"role": "user", "content": [{"text": prompt.user_prompt}]}],
            "inferenceConfig": {"maxTokens": settings.BEDROCK_MAX_OUTPUT_TOKENS},
            "guardrailConfig": {
                "guardrailIdentifier": settings.BEDROCK_GUARDRAIL_ID,
                "guardrailVersion": settings.BEDROCK_GUARDRAIL_VERSION,
            },
        }
        start = perf_counter()
        runtime = get_aws_clients().bedrock_runtime
        primary_model = settings.BEDROCK_MODEL_ARN
        fallback_model = str(settings.BEDROCK_FALLBACK_MODEL_ARN or "").strip()
        fallback_enabled = bool(fallback_model and fallback_model != primary_model)
        circuit_open = fallback_enabled and _primary_circuit_open()
        attempts = [fallback_model] if circuit_open else [primary_model]
        if fallback_enabled and not circuit_open:
            attempts.append(fallback_model)

        response: dict[str, object] | None = None
        model_used = primary_model
        fallback_used = False
        last_error: BaseException | None = None
        for model_id in attempts:
            try:
                response = runtime.converse(modelId=model_id, **params)
                model_used = model_id
                fallback_used = model_id == fallback_model
                if model_id == primary_model:
                    _record_primary_success()
                break
            except (ReadTimeoutError, BotoCoreError, ClientError) as exc:
                last_error = exc
                if model_id == primary_model and _is_transient_bedrock_error(exc):
                    _record_primary_failure()
                    if fallback_enabled:
                        LOGGER.warning(
                            "model_primary_transient_failure_using_fallback",
                            correlation_id=correlation_id,
                            provider=self.name,
                            primary_model=primary_model,
                            fallback_model=fallback_model,
                        )
                        continue
                break

        if response is None:
            if isinstance(last_error, ReadTimeoutError):
                LOGGER.exception("model_timeout", correlation_id=correlation_id, provider=self.name)
                raise BedrockTimeoutError(FALLBACK_RESPONSES["bedrock_error"]) from last_error
            LOGGER.error("model_failed", correlation_id=correlation_id, provider=self.name)
            raise BedrockServiceError(FALLBACK_RESPONSES["bedrock_error"]) from last_error

        latency_ms = int((perf_counter() - start) * 1000)
        finish_reason = str(response.get("stopReason", "") or "")
        failure_layer = "aws_guardrail" if finish_reason == "guardrail_intervened" else None
        if failure_layer:
            LOGGER.warning(
                "aws_guardrail_intervened",
                correlation_id=correlation_id,
                country=prompt.country,
                language=prompt.language,
                provider=self.name,
                finish_reason=finish_reason,
                failure_layer=failure_layer,
            )
        model_response = response_normalizer.from_bedrock_converse(
            response,
            citations=sources,
            confidence=confidence,
            provider=self.name,
            model_name=model_used,
            latency_ms=latency_ms,
            metadata={
                "retrieval": retrieval_result.metadata,
                "prompt_version": prompt.prompt_version,
                "failure_layer": failure_layer,
                "model_fallback_used": fallback_used,
                "primary_circuit_open": circuit_open,
            },
        )
        LOGGER.info(
            "model_success",
            correlation_id=correlation_id,
            country=prompt.country,
            language=prompt.language,
            provider=self.name,
            model=model_used,
            model_fallback_used=fallback_used,
            latency_ms=latency_ms,
            confidence=confidence,
            finish_reason=finish_reason,
            failure_layer=failure_layer,
            **summary,
            sources=source_log_summary(sources),
        )
        return model_response

    def _validate_configuration(self) -> None:
        for name in ["BEDROCK_MODEL_ARN", "BEDROCK_GUARDRAIL_ID", "BEDROCK_GUARDRAIL_VERSION"]:
            if getattr(settings, name).startswith("REPLACE_WITH"):
                raise ConfigurationError(f"{name} is not configured yet.")
