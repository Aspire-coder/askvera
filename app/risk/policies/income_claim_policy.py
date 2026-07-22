"""Income claim risk policy."""

import re

from app.risk.models import PolicyAction, RiskContext, RiskIssue, RiskLevel
from app.risk.rules import RiskPolicyMetadata
from config.guardrail_topics import DENIED_TOPICS


class IncomeClaimPolicy:
    """Flag income and earnings claim language for governance visibility."""

    metadata = RiskPolicyMetadata(
        name="income_claim",
        version="2026.1",
        description="Detects guaranteed-income or earnings-claim language.",
        enabled=True,
        risk_level=RiskLevel.HIGH,
        action=PolicyAction.REFUSE,
    )
    phrases = tuple(DENIED_TOPICS["income_claim"])

    def evaluate(self, context: RiskContext) -> list[RiskIssue]:
        message = (context.user_message or "").lower()
        if not self._contains_income_claim(message):
            return []
        return [
            RiskIssue(
                code="INCOME_CLAIM_RISK",
                message="User message contains income or earnings claim language.",
                level=RiskLevel.HIGH,
                action=PolicyAction.REFUSE,
                source="business_policy",
                policy=self.metadata.name,
                policy_version=self.metadata.version,
            )
        ]

    def _contains_income_claim(self, message: str) -> bool:
        """Detect configured phrases and generic guarantee/earnings combinations."""
        if any(phrase in message for phrase in self.phrases):
            return True
        guarantee = re.search(r"\bguarantee(?:d|s|ing)?\b", message)
        earnings = re.search(
            r"\b(?:earn(?:ed|ing|ings|s)?|income|money|profit|revenue|salary|wage|wages)\b",
            message,
        )
        return bool(guarantee and earnings)
