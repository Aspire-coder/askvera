from app.risk.models import PolicyAction, RiskContext
from app.risk.policies.income_claim_policy import IncomeClaimPolicy
from app.risk.policies.income_claim_translations import is_covered_language
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
    "What would I make per year?",
    "What is the average FBO income?",
    "What do FBOs typically earn?",
    "Could I make enough to quit my job?",
    "Quel est le revenu moyen d’un FBO ?",
])
def test_unconfirmed_income_context_is_kept_for_semantic_review(message) -> None:
    policy = IncomeClaimPolicy()

    assert policy.evaluate(_context(message)) == []
    assert policy.has_income_context(message)


@pytest.mark.parametrize("message", [
    "What is Forever Living Products?",
    "¿Qué es Forever Living Products?",
    "Qu’est-ce que Forever Living Products ?",
    "What is the return policy?",
])
def test_ordinary_questions_have_no_income_context(message) -> None:
    assert not IncomeClaimPolicy().has_income_context(message)


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


# Fix A: bypass-still-works case. A benign question with no income vocabulary,
# in a covered language, must still be eligible for the
# app/retrieval/providers.py bypass (has_income_context False AND
# is_covered_language True) - the whole point of PR #154.
@pytest.mark.parametrize("message", [
    "What is Forever Living Products?",
    "What are the requirements to become a Supervisor?",
])
def test_fix_a_benign_questions_still_qualify_for_bypass(message):
    policy = IncomeClaimPolicy()
    assert not policy.has_income_context(message)
    assert is_covered_language("en", message)


# Fix A: an uncovered language must never qualify for the bypass, even with
# no income vocabulary detected (has_income_context can only find vocabulary
# it has been taught, so "nothing found" for an uncovered language is not
# evidence of anything).
@pytest.mark.parametrize(
    ("message", "language"),
    [
        ("Ile moge zarobic?", "pl"),
        ("Ayda ne kadar kazanabilirim?", "tr"),
        ("Berapa penghasilan yang bisa saya dapatkan?", "id"),
        ("Toi co the kiem duoc bao nhieu tien?", "vi"),
        ("Ninaweza kupata pesa ngapi?", "sw"),
    ],
)
def test_fix_a_uncovered_language_never_bypasses(message, language):
    assert not is_covered_language(language, message)


# Fix A: a non-Latin script the covered languages never write in must not
# bypass even when the request declares a covered language, because a user
# can type any language regardless of the widget's configured locale.
@pytest.mark.parametrize(
    "message",
    [
        "كم سوف اربح؟",  # Arabic
        "每月能赚多少钱？",  # Chinese
    ],
)
def test_fix_a_uncovered_script_never_bypasses_even_for_covered_language(message):
    assert not is_covered_language("en", message)


# Fix A: the confirmed English misses from the offline probe (2026-09-15) -
# job-replacement/financial-independence phrasing with no earnings, money,
# guarantee, or gain/prize word - must now keep independent semantic review
# instead of silently reaching retrieval.
@pytest.mark.parametrize("message", [
    "Is this a way to replace my full time job?",
    "Will I be financially independent doing this?",
    "Could this support my family?",
    "Will this replace my nine to five?",
    "Is this how people become financially free?",
])
def test_fix_a_oblique_job_replacement_phrasing_keeps_context(message):
    policy = IncomeClaimPolicy()
    assert policy.has_income_context(message)
    # And explicitly not a confirmed refusal on its own - only context.
    assert policy.evaluate(_context(message)) == []


# Fix A must not widen refusal: a confirmed guarantee/earnings pairing keeps
# refusing exactly as before, whether or not it happens to also use the new
# job-replacement wording.
@pytest.mark.parametrize("message", [
    "Can I get guaranteed income with this business?",
    "I guarantee you will earn enough to replace your full time job.",
])
def test_fix_a_does_not_weaken_confirmed_income_refusal(message):
    issues = IncomeClaimPolicy().evaluate(_context(message))
    assert len(issues) == 1
    assert issues[0].action == PolicyAction.REFUSE
