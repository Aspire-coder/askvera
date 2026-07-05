"""Income claim risk policy."""

from app.risk.models import RiskContext, RiskIssue, RiskLevel
from app.risk.rules import RiskPolicyMetadata


class IncomeClaimPolicy:
    """Flag income and earnings claim language for governance visibility."""

    metadata = RiskPolicyMetadata(
        name="income_claim",
        version="2026.1",
        description="Detects guaranteed-income or earnings-claim language.",
        enabled=True,
        risk_level=RiskLevel.HIGH,
    )
    phrases = ("guaranteed income", "get rich", "earnings guarantee", "passive income")

    def evaluate(self, context: RiskContext) -> list[RiskIssue]:
        message = (context.user_message or "").lower()
        if not any(phrase in message for phrase in self.phrases):
            return []
        return [
            RiskIssue(
                code="INCOME_CLAIM_RISK",
                message="User message contains income or earnings claim language.",
                level=RiskLevel.HIGH,
                source="business_policy",
                policy=self.metadata.name,
                policy_version=self.metadata.version,
            )
        ]
