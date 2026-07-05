"""Medical claim risk policy."""

from app.risk.models import PolicyAction, RiskContext, RiskIssue, RiskLevel
from app.risk.rules import RiskPolicyMetadata


class MedicalClaimPolicy:
    """Flag medical and disease-related claims for governance visibility."""

    metadata = RiskPolicyMetadata(
        name="medical_claim",
        version="2026.1",
        description="Detects medical, disease, cure, treatment, or prevention language.",
        enabled=True,
        risk_level=RiskLevel.HIGH,
        action=PolicyAction.WARN,
    )
    phrases = ("cure", "treat", "prevent disease", "diabetes", "cancer")

    def evaluate(self, context: RiskContext) -> list[RiskIssue]:
        message = (context.user_message or "").lower()
        if not any(phrase in message for phrase in self.phrases):
            return []
        return [
            RiskIssue(
                code="MEDICAL_CLAIM_RISK",
                message="User message contains medical or disease-related claim language.",
                level=RiskLevel.HIGH,
                action=PolicyAction.WARN,
                source="business_policy",
                policy=self.metadata.name,
                policy_version=self.metadata.version,
            )
        ]
