"""Model provider interface."""

from typing import Protocol

from app.prompts import PromptPackage
from app.retrieval import RetrievalResult

from .responses import ModelResponse


class ModelProvider(Protocol):
    """Interface implemented by all model providers."""

    name: str

    def generate(self, prompt: PromptPackage, retrieval_result: RetrievalResult, correlation_id: str) -> ModelResponse:
        """Generate a model response from a prompt package."""
        ...
