"""Income earnings-projection risk policy.

This is a TIGHTENING of governance for GENERATED answers only: it never
changes anything about the user-input pass. It only adds a refusal for
answer text that makes an earnings projection (a specific or estimated
amount attributed to FBOs/roles/"most"/"you") that IncomeClaimPolicy's
guarantee/earnings-phrase matching does not already catch.

Design constraints (do not relax):
  - Acts only when context.is_generated_answer is True.
  - is_claim_topic is False, so RiskEngine.allow_claim_topics forgiveness
    (which only ever applies to is_claim_topic policies) can never suppress
    it.
  - Defers -- emits nothing -- when IncomeClaimPolicy already refuses this
    same context AND allow_claim_topics is False, so a text IncomeClaimPolicy
    already handles under that condition never changes its outcome or gets a
    second, duplicate issue. When allow_claim_topics is True, IncomeClaimPolicy's
    own issue may itself be suppressed by RiskEngine's claim-topic exemption,
    so this policy still runs its own detector rather than assuming the
    other policy's issue stands.

RiskEngine (app/risk/engine.py) runs every policy's evaluate(context)
independently and has no cross-policy channel in RiskContext, so the
deferral above is implemented by composition: this policy asks a private
IncomeClaimPolicy instance to evaluate the same context, exactly as the
engine will, rather than reading a state field.
"""

from __future__ import annotations

from app.risk.models import PolicyAction, RiskContext, RiskIssue, RiskLevel
from app.risk.policies.income_claim_policy import IncomeClaimPolicy
from app.risk.policies.income_projection import detect_earnings_projection
from app.risk.rules import RiskPolicyMetadata


class IncomeProjectionPolicy:
    """Flag unqualified earnings-projection language in generated answers."""

    metadata = RiskPolicyMetadata(
        name="income_projection",
        version="2026.1",
        description=(
            "Detects earnings-projection language (specific or estimated amounts attributed to "
            "FBOs/roles) in generated answers."
        ),
        enabled=True,
        risk_level=RiskLevel.HIGH,
        action=PolicyAction.REFUSE,
        is_claim_topic=False,
    )

    def __init__(self, income_claim_policy: IncomeClaimPolicy | None = None) -> None:
        self._income_claim_policy = income_claim_policy or IncomeClaimPolicy()

    def evaluate(self, context: RiskContext) -> list[RiskIssue]:
        if not context.is_generated_answer:
            return []
        if not context.allow_claim_topics and self._income_claim_policy.evaluate(context):
            # IncomeClaimPolicy already refuses this same answer and nothing
            # will suppress that refusal, so do not add a duplicate finding
            # or otherwise change this pass's outcome.
            return []
        if not detect_earnings_projection(context.user_message or "", context.language):
            return []
        return [
            RiskIssue(
                code="INCOME_PROJECTION_RISK",
                message="Generated answer contains an earnings-projection statement.",
                level=RiskLevel.HIGH,
                action=PolicyAction.REFUSE,
                source="business_policy",
                policy=self.metadata.name,
                policy_version=self.metadata.version,
            )
        ]
