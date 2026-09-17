"""Risk and policy engine."""

from services.guardrails import asserts_denied_claim

from .models import RiskContext, RiskDecision
from .policies import CountryPolicy, IncomeClaimPolicy, InputLengthPolicy, MedicalClaimPolicy
from .rules import RiskPolicy


class RiskEngine:
    """Execute registered risk policies and aggregate their findings."""

    def __init__(self, policies: list[RiskPolicy] | None = None) -> None:
        self.policies = policies or []

    def evaluate(self, context: RiskContext) -> RiskDecision:
        """Run all enabled policies against the context.

        Every policy always runs. context.allow_claim_topics does not skip one;
        it only lets a CLAIM-TOPIC policy (medical_claim, income_claim) forgive
        an answer whose own text denies the claim it names, which is what an
        explanation of a prohibition looks like. The claim-topic policies match
        by plain substring, so they cannot tell "Forever prohibits promising
        guaranteed income" from "you will earn guaranteed income"; the clause
        reading in asserts_denied_claim can, and is the same rule the guardrail
        provider applies, so the two layers cannot disagree about what counts as
        a claim.

        An answer that does assert the claim keeps its issue and is refused,
        however the question was phrased. Every other policy is untouched.
        """
        decision = RiskDecision()
        for policy in self.policies:
            if not policy.metadata.enabled:
                continue
            issues = list(policy.evaluate(context))
            if (
                issues
                and context.allow_claim_topics
                and policy.metadata.is_claim_topic
                and not asserts_denied_claim(policy.metadata.name, context.user_message or "")
            ):
                continue
            for issue in issues:
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
