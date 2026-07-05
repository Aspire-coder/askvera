"""Input length risk policy."""

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
    max_length = 25000

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
