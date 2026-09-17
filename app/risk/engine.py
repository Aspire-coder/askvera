"""Risk and policy engine."""

from .models import RiskContext, RiskDecision
from .policies import CountryPolicy, IncomeClaimPolicy, InputLengthPolicy, MedicalClaimPolicy
from .rules import RiskPolicy


class RiskEngine:
    """Execute registered risk policies and aggregate their findings."""

    def __init__(self, policies: list[RiskPolicy] | None = None) -> None:
        self.policies = policies or []

    def evaluate(self, context: RiskContext) -> RiskDecision:
        """Run all enabled policies against the context.

        context.allow_claim_topics skips policies whose metadata marks them
        is_claim_topic (medical_claim, income_claim). Every other policy,
        off_topic included -- off_topic has no risk policy at all -- still
        runs unconditionally.
        """
        decision = RiskDecision()
        for policy in self.policies:
            if not policy.metadata.enabled:
                continue
            if context.allow_claim_topics and policy.metadata.is_claim_topic:
                continue
            for issue in policy.evaluate(context):
                decision.add_issue(issue)
        return decision


def default_policies() -> list[RiskPolicy]:
    """Return the default risk policy sequence."""
    return [
        InputLengthPolicy(),
        MedicalClaimPolicy(),
        IncomeClaimPolicy(),
        CountryPolicy(),
    ]


risk_engine = RiskEngine(default_policies())
