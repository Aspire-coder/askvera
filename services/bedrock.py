"""Compatibility wrappers for Bedrock model generation."""

from typing import Any

from app.models import ModelResponse, model_router
from app.prompts import PromptBuilder, PromptPackage
from app.retrieval import RetrievalResult, confidence_from_sources, retrieval_service
from config import settings
from utils.exceptions import ConfigurationError


def _confidence_from_sources(sources: list[dict[str, Any]]) -> float:
    """Compatibility wrapper for existing tests and transitional callers."""
    return confidence_from_sources(sources)


def generate(prompt_package: PromptPackage, retrieval_result: RetrievalResult, correlation_id: str) -> dict[str, Any]:
    """Compatibility wrapper around the configured model router."""
    response: ModelResponse = model_router.generate(prompt_package, retrieval_result, correlation_id)
    return response.to_chat_result()


def retrieve_and_generate(
    message: str,
    country: str,
    language: str,
    role: str,
    session_history: str,
    correlation_id: str,
    prompt_package: PromptPackage | None = None,
    retrieval_result: RetrievalResult | None = None,
) -> dict[str, Any]:
    """Compatibility wrapper around retrieval, prompt building, and generation."""
    for name in ["BEDROCK_KB_ID", "BEDROCK_MODEL_ARN", "BEDROCK_GUARDRAIL_ID", "BEDROCK_GUARDRAIL_VERSION"]:
        if getattr(settings, name).startswith("REPLACE_WITH"):
            raise ConfigurationError(f"{name} is not configured yet.")
    if retrieval_result is None:
        retrieval_result = retrieval_service.retrieve(message, country, language, role, correlation_id)
    if prompt_package is None:
        prompt_package = PromptBuilder().build(
            user_question=message,
            conversation=session_history,
            country=country,
            language=language,
            role=role,
            retrieval_result=retrieval_result,
        )
    return generate(prompt_package, retrieval_result, correlation_id)
