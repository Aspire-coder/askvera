"""Bedrock Guardrails governance provider wrapper."""

from services.guardrails import check_text
from utils.exceptions import GuardrailBlockedError

from ..models import GovernanceAction, GovernanceDecision


class BedrockGuardrailsProvider:
    """Wrap existing guardrail checks in the governance provider interface."""

    name = "bedrock_guardrails"

    def evaluate(
        self,
        *,
        text: str,
        country: str,
        language: str,
        correlation_id: str,
    ) -> GovernanceDecision:
        """Evaluate text using the existing guardrail service."""
        try:
            check_text(text, correlation_id)
        except GuardrailBlockedError as exc:
            return GovernanceDecision(
                allowed=False,
                action=GovernanceAction.BLOCK,
                provider=self.name,
                reason=exc.message,
                guardrail_action=GovernanceAction.BLOCK,
                metadata={
                    "country": country,
                    "language": language,
                    "errorCode": exc.error_code,
                    "topic": exc.topic,
                },
            )
        return GovernanceDecision(
            allowed=True,
            action=GovernanceAction.ALLOW,
            provider=self.name,
            guardrail_action=GovernanceAction.ALLOW,
            metadata={
                "country": country,
                "language": language,
            },
        )
