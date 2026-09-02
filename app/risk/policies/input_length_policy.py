"""Input length risk policy."""

from config import settings

from app.risk.models import PolicyAction, RiskContext, RiskIssue, RiskLevel
from app.risk.rules import RiskPolicyMetadata


class InputLengthPolicy:
    """Block extremely large prompts before retrieval and model execution."""

    metadata = RiskPolicyMetadata(
        name="input_length",
        version="2026.1",
        description="Detects oversized user prompts that may affect stability or cost.",
        enabled=True,
        risk_level=RiskLevel.CRITICAL,
        action=PolicyAction.REFUSE,
    )

    @property
    def max_length(self) -> int:
        # Read live rather than caching at class-definition time, so an SSM
        # config reload after this module first imports still takes effect.
        return settings.RISK_INPUT_MAX_CHARS

    def evaluate(self, context: RiskContext) -> list[RiskIssue]:
        if len(context.user_message or "") <= self.max_length:
            return []
        return [
            RiskIssue(
                code="INPUT_TOO_LONG",
                message="User message exceeds maximum risk policy length.",
                level=RiskLevel.CRITICAL,
                action=PolicyAction.REFUSE,
                source="input",
                policy=self.metadata.name,
                policy_version=self.metadata.version,
            )
        ]
