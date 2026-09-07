from app.risk.models import PolicyAction, RiskContext
from app.risk.policies.income_claim_policy import IncomeClaimPolicy
import pytest


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


@pytest.mark.parametrize("message", [
    "Once you've earned a Sales Level, you keep it. Maintaining one status doesn't guarantee the other.",
    "Earning your sales rank does not guarantee Active status.",
    "You earn Active status monthly. This does not guarantee retention of another status.",
    "There is no re-qualifying needed for the Sales Level itself once earned. "
    "Maintaining one doesn't guarantee the other.",
])
def test_earned_status_is_not_earnings(message):
    assert IncomeClaimPolicy().evaluate(_context(message)) == []


@pytest.mark.parametrize("message", [
    "You earned your sales rank. I guarantee you will earn $5000 every month.",
    "Earning a sales level guarantees income.",
    "Your rank doesn't guarantee Active status, but I guarantee money every month.",
    "I guarantee you will earn. You already earned your rank.",
    "You earned your rank. Guaranteed earnings are available.",
    "Earn a sales rank and earn $5000, guaranteed.",
    "The Sales Level is earned. Guaranteed income follows.",
    "You earned a sales level. I guarantee $5000 every month.",
    "You earned your rank. This guarantees bonuses.",
])
def test_status_language_cannot_hide_real_income_claim(message):
    assert IncomeClaimPolicy().evaluate(_context(message))
