"""Bedrock Claude model provider."""

from time import perf_counter

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
        if confidence < settings.BEDROCK_MIN_CONFIDENCE and not strong_local_match:
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
            "modelId": settings.BEDROCK_MODEL_ARN,
            "system": [{"text": prompt.system_prompt}],
            "messages": [{"role": "user", "content": [{"text": prompt.user_prompt}]}],
            "guardrailConfig": {
                "guardrailIdentifier": settings.BEDROCK_GUARDRAIL_ID,
                "guardrailVersion": settings.BEDROCK_GUARDRAIL_VERSION,
            },
        }
        start = perf_counter()
        try:
            response = get_aws_clients().bedrock_runtime.converse(**params)
        except ReadTimeoutError as exc:
            LOGGER.exception("model_timeout", correlation_id=correlation_id, provider=self.name)
            raise BedrockTimeoutError(FALLBACK_RESPONSES["bedrock_error"]) from exc
        except (BotoCoreError, ClientError) as exc:
            LOGGER.exception("model_failed", correlation_id=correlation_id, provider=self.name)
            raise BedrockServiceError(FALLBACK_RESPONSES["bedrock_error"]) from exc

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
            model_name=settings.BEDROCK_MODEL_ARN,
            latency_ms=latency_ms,
            metadata={
                "retrieval": retrieval_result.metadata,
                "prompt_version": prompt.prompt_version,
                "failure_layer": failure_layer,
            },
        )
        LOGGER.info(
            "model_success",
            correlation_id=correlation_id,
            country=prompt.country,
            language=prompt.language,
            provider=self.name,
            model=settings.BEDROCK_MODEL_ARN,
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
