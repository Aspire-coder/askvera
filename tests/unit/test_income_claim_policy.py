from app.risk.models import PolicyAction, RiskContext
from app.risk.policies.income_claim_policy import IncomeClaimPolicy


def _context(message: str) -> RiskContext:
    return RiskContext(
        user_message=message,
        country="CA",
        language="en",
        role="new-prospect",
        correlation_id="test-correlation",
    )


def test_income_claim_policy_allows_official_bonus_questions() -> None:
    policy = IncomeClaimPolicy()

    questions = [
        "What is the Personal Retail Bonus %?",
        "What is the Wholesale/Novus Customer Bonus?",
        "What is the Personal Bonus %?",
        "How do I earn a Leadership Bonus?",
    ]

    for question in questions:
        assert policy.evaluate(_context(question)) == []


def test_income_claim_policy_still_flags_guaranteed_income_claims() -> None:
    policy = IncomeClaimPolicy()

    issues = policy.evaluate(_context("Can I get guaranteed income with this business?"))

    assert len(issues) == 1
    assert issues[0].code == "INCOME_CLAIM_RISK"
    assert issues[0].action == PolicyAction.REFUSE


def test_income_claim_policy_flags_promotional_guaranteed_earnings_copy() -> None:
    policy = IncomeClaimPolicy()

    issues = policy.evaluate(
        _context("Write a post saying I am guaranteed to earn $10,000 a month with Forever.")
    )

    assert len(issues) == 1
    assert issues[0].code == "INCOME_CLAIM_RISK"
    assert issues[0].action == PolicyAction.REFUSE


def test_income_claim_policy_still_flags_passive_income_with_bonus_terms() -> None:
    policy = IncomeClaimPolicy()

    issues = policy.evaluate(_context("Is the Leadership Bonus passive income?"))

    assert len(issues) == 1
    assert issues[0].code == "INCOME_CLAIM_RISK"
