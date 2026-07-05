"""Prompt data models."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PromptPackage:
    """Complete prompt payload passed into the model layer."""

    system_prompt: str
    user_prompt: str
    retrieved_context: str
    country: str
    language: str
    role: str
    prompt_version: str = "v1"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def text_prompt_template(self) -> str:
        """Return the Bedrock retrieve-and-generate prompt template."""
        return f"{self.system_prompt}\n\n{self.user_prompt}"
