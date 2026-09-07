"""Income claim risk policy."""

import re

from app.risk.models import PolicyAction, RiskContext, RiskIssue, RiskLevel
from app.risk.rules import RiskPolicyMetadata
from config.guardrail_topics import DENIED_TOPICS
from services.guardrails import is_policy_safety_question


# Recognize status context, but never remove earnings words: doing so can
# hide a later dollar/bonus guarantee in the same message.
EARNED_STATUS_RE = re.compile(
    r"\bearn(?:ed|ing|s)?\s+(?:(?:a|an|the|my|your|their|our|his|her)\s+)?"
    r"(?:sales\s+(?:level|rank)|rank|active\s+status)\b"
    r"|\b(?:sales\s+(?:level|rank)|rank|active\s+status)\s+"
    r"(?:itself\s+)?(?:once|is|was|has\s+been)\s+earned\b",
    re.IGNORECASE,
)
NEGATED_STATUS_GUARANTEE_RE = re.compile(
    r"\b(?:does\s+not|doesn['’]t|do\s+not|don['’]t)\s+guarantee\s+"
    r"(?:active\s+status|the\s+other|retention\s+of\s+another\s+status)\b",
    re.IGNORECASE,
)


class IncomeClaimPolicy:
    """Flag income and earnings claim language for governance visibility."""

    metadata = RiskPolicyMetadata(
        name="income_claim",
        version="2026.2",
        description="Detects guaranteed-income or earnings-claim language.",
        enabled=True,
        risk_level=RiskLevel.HIGH,
        action=PolicyAction.REFUSE,
    )
    phrases = tuple(DENIED_TOPICS["income_claim"])

    def evaluate(self, context: RiskContext) -> list[RiskIssue]:
        message = (context.user_message or "").lower()
        if is_policy_safety_question(message):
            return []
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
        # Only exclude an explicit denial about status when the text actually
        # discusses earning a status. Positive guarantees anywhere still count.
        guarantee_text = (
            NEGATED_STATUS_GUARANTEE_RE.sub(" ", message)
            if EARNED_STATUS_RE.search(message) else message
        )
        guarantee = re.search(r"\bguarantee(?:d|s|ing)?\b", guarantee_text)
        earnings = re.search(
            r"\b(?:earn(?:ed|ing|ings|s)?|income|money|profit|revenue|salary|wage|wages)\b",
            message,
        )
        return bool(guarantee and earnings)
