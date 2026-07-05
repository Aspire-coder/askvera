"""Model provider interface."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from .responses import ModelResponse

if TYPE_CHECKING:
    from app.prompts.models import PromptPackage
    from app.retrieval.models import RetrievalResult


class ModelProvider(Protocol):
    """Interface implemented by all model providers."""

    name: str

    def generate(self, prompt: PromptPackage, retrieval_result: RetrievalResult, correlation_id: str) -> ModelResponse:
        """Generate a model response from a prompt package."""
        ...
