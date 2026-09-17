"""Unit tests for RiskEngine's allow_claim_topics suppression.

RiskContext.allow_claim_topics skips policies whose metadata marks
is_claim_topic (medical_claim, income_claim) so a governance pass over a
generated answer that explains a reviewed policy is not refused for using
the vocabulary of the rule it explains. Every other policy -- including
country_support and input_length, which stand in for "everything that is
not a claim topic" since off_topic has no risk policy at all -- must keep
running regardless of the flag.
"""

from app.risk.engine import RiskEngine, default_policies
from app.risk.models import PolicyAction, RiskContext
from app.risk.policies.income_claim_policy import IncomeClaimPolicy
from app.risk.policies.medical_claim_policy import MedicalClaimPolicy


def _context(message: str, *, allow_claim_topics: bool = False, country: str = "US") -> RiskContext:
    return RiskContext(
        user_message=message,
        country=country,
        language="en",
        role="new_prospect",
        correlation_id="test-correlation",
        allow_claim_topics=allow_claim_topics,
    )


def test_medical_and_income_policies_are_marked_as_claim_topics() -> None:
    assert MedicalClaimPolicy.metadata.is_claim_topic is True
    assert IncomeClaimPolicy.metadata.is_claim_topic is True


def test_engine_suppresses_income_claim_when_allow_claim_topics_is_set() -> None:
    engine = RiskEngine(default_policies())
    message = "Can I get guaranteed income with this business?"

    refused = engine.evaluate(_context(message))
    assert refused.should_refuse() is True
    assert any(issue.code == "INCOME_CLAIM_RISK" for issue in refused.issues)

    exempted = engine.evaluate(_context(message, allow_claim_topics=True))
    assert exempted.should_refuse() is False
    assert not any(issue.code == "INCOME_CLAIM_RISK" for issue in exempted.issues)


def test_engine_suppresses_medical_claim_when_allow_claim_topics_is_set() -> None:
    engine = RiskEngine(default_policies())
    message = "Explaining 16.02(j): we may not say our products cure or treat disease."

    with_issue = engine.evaluate(_context(message))
    assert any(issue.code == "MEDICAL_CLAIM_RISK" for issue in with_issue.issues)

    exempted = engine.evaluate(_context(message, allow_claim_topics=True))
    assert not any(issue.code == "MEDICAL_CLAIM_RISK" for issue in exempted.issues)


def test_allow_claim_topics_does_not_affect_unrelated_policies() -> None:
    """country_support (a stand-in for off_topic -- neither is a claim topic) still runs."""
    engine = RiskEngine(default_policies())

    decision = engine.evaluate(_context("hello there", allow_claim_topics=True, country="ZZ"))

    assert decision.should_refuse() is True
    assert any(issue.code == "UNSUPPORTED_COUNTRY" for issue in decision.issues)


def test_allow_claim_topics_default_is_false_and_changes_nothing() -> None:
    engine = RiskEngine(default_policies())
    message = "Can I get guaranteed income with this business?"

    default_decision = engine.evaluate(
        RiskContext(
            user_message=message,
            country="US",
            language="en",
            role="new_prospect",
            correlation_id="test-correlation",
        )
    )

    assert default_decision.action == PolicyAction.REFUSE
