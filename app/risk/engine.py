"""Risk and policy engine."""

from .models import RiskContext, RiskDecision
from .policies import CountryPolicy, IncomeClaimPolicy, InputLengthPolicy, MedicalClaimPolicy
from .rules import RiskPolicy


class RiskEngine:
    """Execute registered risk policies and aggregate their findings."""

    def __init__(self, policies: list[RiskPolicy] | None = None) -> None:
        self.policies = policies or []

    def evaluate(self, context: RiskContext) -> RiskDecision:
        """Run all enabled policies against the context."""
        decision = RiskDecision()
        for policy in self.policies:
            if not policy.metadata.enabled:
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
