"""The return-policy answer with an FBO buyback section is not an income claim.

Live diagnostic case 15 (candidate 0eb5493, 2026-09-12): a US session asked "What is the return policy?". The model's
answer was correct, then refused on the answer path by the income rule (failure_layer risk_policy), so the user saw
"I can't share income projections or guarantees ...". The answer says "**100% product satisfaction is guaranteed.**"
for customers and, in a separate FBO buyback section, that "profit is deducted from your refund" and a refund is
"minus bonuses you personally received".

Two things combined. "satisfaction is guaranteed" (a verb between) was not recognised as a consumer guarantee at all,
so "guaranteed" paired with "profit" anywhere in the text; and profit or bonuses that are deducted from a refund were
still read as money words. Now a copula satisfaction guarantee is set aside only when every earnings, money or
currency word in the whole text is refund or deduction wording, and deduction wording ("profit is deducted", "minus
bonuses") no longer counts as a money word next to a consumer guarantee.

Everything here is local: the risk engine and the local denied-phrase guardrail. Network sockets and boto3 clients
raise if anything tries to use them.
"""

from __future__ import annotations

import socket

import pytest

from app.governance import governance_engine
from app.governance.models import GovernanceDecision
from app.risk.models import RiskContext
from app.risk.policies.income_claim_policy import IncomeClaimPolicy


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def _refuse(*_: object, **__: object):
        raise AssertionError("network access attempted in an offline test")

    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)
    try:
        import boto3
        import boto3.session
    except ImportError:  # pragma: no cover - boto3 is a runtime dependency
        return
    monkeypatch.setattr(boto3, "client", _refuse)
    monkeypatch.setattr(boto3.session.Session, "client", _refuse)


# Verbatim pre-refusal answer text (scratch int5-live/check15_pre_repair.txt).
LIVE_RETURN_POLICY_ANSWER = (
    "# Forever Living's Return Policy\n"
    "\n"
    "Forever Living offers strong protections for both customers and business partners:\n"
    "\n"
    "## For Retail/Preferred Customers\n"
    "\n"
    "**100% product satisfaction is guaranteed.** Within 30 days from the date of purchase, you may either:\n"
    "- Obtain a new replacement for any defective product, or\n"
    "- Cancel the purchase, return the product, and receive a full refund of the purchase price (excluding shipping).\n"
    "\n"
    "You'll need to provide proper notice, proof of purchase, and return the product timely to your source of "
    "purchase. Forever Living reserves the right to reject repetitive returns.\n"
    "\n"
    "## For Forever Living Business Owners (FBOs)\n"
    "\n"
    "**FLP will buy back unsold, salable products** (except literature) purchased within the previous 12 months. "
    "You'll need to return all products and provide proof of purchase.\n"
    "\n"
    "When you return products:\n"
    "- If purchased at Preferred Customer Price, that profit is deducted from your refund\n"
    "- If the return is greater than 1 Case Credit, bonuses and Case Credits received by your upline are deducted "
    "from them\n"
    "- You receive a refund check equal to your cost of the products, minus bonuses you personally received\n"
    "\n"
    "**Important note:** If products were acquired through an FBO (rather than directly from the company webstore), "
    "that FBO is the primary party responsible for handling customer satisfaction, exchanges, and refunds.\n"
    "\n"
    "Is there a specific return scenario you'd like to understand better?"
)
_BLOCKS = LIVE_RETURN_POLICY_ANSWER.split("\n\n")
# 0 title, 1 intro, 2 customer heading, 3 guarantee + bullets, 4 notice, 5 FBO heading, 6 buyback, 7 deductions,
# 8 important note, 9 closing question.
assert len(_BLOCKS) == 10 and _BLOCKS[5].startswith("## For Forever Living Business Owners")

NO_HEADINGS = "\n\n".join(block for block in _BLOCKS if not block.startswith("#"))
STAR_BULLETS = LIVE_RETURN_POLICY_ANSWER.replace("\n- ", "\n* ")
FBO_BLOCK_FIRST = "\n\n".join(_BLOCKS[index] for index in (0, 1, 5, 6, 7, 2, 3, 4, 8, 9))
FBO_BLOCK_FIRST_NO_HEADINGS = "\n\n".join(_BLOCKS[index] for index in (1, 6, 7, 3, 4, 8, 9))
CRLF = LIVE_RETURN_POLICY_ANSWER.replace("\n", "\r\n")

LIVE_VARIANTS = [LIVE_RETURN_POLICY_ANSWER, NO_HEADINGS, STAR_BULLETS, FBO_BLOCK_FIRST, FBO_BLOCK_FIRST_NO_HEADINGS,
                 CRLF]
LIVE_VARIANT_IDS = ["live", "no_headings", "star_bullets", "fbo_first", "fbo_first_no_headings", "crlf"]

ALLOWED_CONTROLS = [
    "Satisfaction is guaranteed.\n\nThe profit is deducted from your refund.",
    "Customer satisfaction is guaranteed; the profit on a returned order is charged back to the FBO.",
    "100% product satisfaction is guaranteed. You receive a refund equal to your cost, minus bonuses you received.",
]

EARNINGS_PROMISE = "You are guaranteed to earn $5,000 a month."

BLOCKED = [
    # Required by the brief: the live answer with an earnings promise in either paragraph.
    LIVE_RETURN_POLICY_ANSWER.replace(
        "reject repetitive returns.", f"reject repetitive returns. {EARNINGS_PROMISE}"),
    LIVE_RETURN_POLICY_ANSWER.replace(
        "and provide proof of purchase.\n\nWhen", f"and provide proof of purchase. {EARNINGS_PROMISE}\n\nWhen"),
    LIVE_RETURN_POLICY_ANSWER.replace(
        "minus bonuses you personally received", f"minus bonuses you personally received. {EARNINGS_PROMISE}"),
    LIVE_RETURN_POLICY_ANSWER.replace(
        "**100% product satisfaction is guaranteed.**", f"**100% product satisfaction is guaranteed.** {EARNINGS_PROMISE}"),
    "Guaranteed satisfaction.\n\nYou'll earn $5,000 a month.",
    "100% satisfaction guaranteed.\n\n## Income\nWe guarantee you will make money.",
    # A guarantee block and a separate block that promises income, profit, bonuses or wealth.
    LIVE_RETURN_POLICY_ANSWER + "\n\nJoin and your bonuses are guaranteed.",
    LIVE_RETURN_POLICY_ANSWER + "\n\nJoin and your profit is guaranteed.",
    LIVE_RETURN_POLICY_ANSWER + "\n\n## Income\nWe guarantee you will make money.",
    LIVE_RETURN_POLICY_ANSWER + "\n\nJoin and you will become wealthy.",
    LIVE_RETURN_POLICY_ANSWER + "\n\nFBOs are guaranteed a monthly income.",
    FBO_BLOCK_FIRST_NO_HEADINGS + "\n\nJoin and your bonuses are guaranteed.",
    "100% product satisfaction is guaranteed.\n\nYou will make a profit every month.",
    "100% product satisfaction is guaranteed.\n\n## For FBOs\n\nJoin the team today and after a few months you will "
    "make a lot of money.",
    "Satisfaction is guaranteed. Join the team today and after a few months you will make a lot of money.",
    "Your satisfaction is guaranteed and so is your profit.",
    "Customer satisfaction will be 100% guaranteed, and so will your revenue.",
    # The deduction lines turned into promises: profit or bonuses that are paid, added or not deducted still count.
    LIVE_RETURN_POLICY_ANSWER.replace("that profit is deducted from your refund", "that profit is paid to you monthly"),
    LIVE_RETURN_POLICY_ANSWER.replace("minus bonuses you personally received", "plus bonuses you personally received"),
    LIVE_RETURN_POLICY_ANSWER.replace("that profit is deducted from your refund",
                                      "that profit is not deducted from your refund"),
    # Deduction wording that hides a claim: a negation, a gain or prize in its clause, an earnings word inside it, an
    # amount, a second guarantee, or money outside it.
    "Product satisfaction is guaranteed, and no profit is deducted from your refund.",
    "Product satisfaction is guaranteed; your profit is deducted from your refund plus a new car every month.",
    "Product satisfaction is guaranteed. Commission revenue is withheld until you join.",
    "Product satisfaction is guaranteed. Profit of 5,000 dollars is deducted from your refund.",
    "100% satisfaction is guaranteed. Profit is deducted from your refund. Guaranteed profit for FBOs.",
    "Money-back guarantee. Your profit is deducted from your refund and you will make money.",
    "Satisfaction is guaranteed; profit is deducted from your refund. Most FBOs make money within a year of joining.",
]

# Narrowness guard: deduction wording is relief for the copula satisfaction guarantee only. Other consumer guarantees
# and warranties next to deduction wording keep their 0eb5493 verdict (refused).
CONSERVATIVE_REFUSED_AS_ON_0EB5493 = [
    "The guarantee covers defects; the profit is deducted from your refund.",
    "Satisfaction guaranteed; the profit is deducted from your refund.",
    "Money-back guarantee. The profit is deducted from your refund.",
]


def _context(text: str) -> RiskContext:
    return RiskContext(user_message=text, country="US", language="en", role="new_prospect", correlation_id="cid")


def _evaluate(text: str, *, answer: bool) -> GovernanceDecision:
    return governance_engine.evaluate(
        text=text, country="US", language="en", correlation_id="cid", is_generated_answer=answer,
    )


@pytest.mark.parametrize("text", LIVE_VARIANTS, ids=LIVE_VARIANT_IDS)
def test_live_return_policy_answer_is_not_an_income_claim_for_the_policy(text) -> None:
    assert IncomeClaimPolicy()._contains_income_claim(text.lower()) is False
    assert IncomeClaimPolicy().evaluate(_context(text)) == []


@pytest.mark.parametrize("answer", [False, True], ids=["input", "generated_answer"])
@pytest.mark.parametrize("text", LIVE_VARIANTS, ids=LIVE_VARIANT_IDS)
def test_live_return_policy_answer_passes_governance(text, answer) -> None:
    decision = _evaluate(text, answer=answer)
    assert decision.allowed is True, decision


@pytest.mark.parametrize("answer", [False, True], ids=["input", "generated_answer"])
@pytest.mark.parametrize("text", ALLOWED_CONTROLS)
def test_deduction_wording_next_to_a_satisfaction_guarantee_is_allowed(text, answer) -> None:
    assert IncomeClaimPolicy().evaluate(_context(text)) == []
    decision = _evaluate(text, answer=answer)
    assert decision.allowed is True, decision


@pytest.mark.parametrize("text", BLOCKED)
def test_income_promises_beside_the_return_policy_are_flagged_by_the_policy(text) -> None:
    issues = IncomeClaimPolicy().evaluate(_context(text))
    assert [issue.code for issue in issues] == ["INCOME_CLAIM_RISK"]


@pytest.mark.parametrize("answer", [False, True], ids=["input", "generated_answer"])
@pytest.mark.parametrize("text", BLOCKED)
def test_income_promises_beside_the_return_policy_are_refused_by_governance(text, answer) -> None:
    decision = _evaluate(text, answer=answer)
    assert decision.allowed is False
    assert decision.provider == "risk_engine"
    assert [issue["code"] for issue in decision.metadata["risk"]["issues"]] == ["INCOME_CLAIM_RISK"]


@pytest.mark.parametrize("answer", [False, True], ids=["input", "generated_answer"])
@pytest.mark.parametrize("text", CONSERVATIVE_REFUSED_AS_ON_0EB5493)
def test_deduction_relief_is_only_for_the_copula_satisfaction_guarantee(text, answer) -> None:
    assert [issue.code for issue in IncomeClaimPolicy().evaluate(_context(text))] == ["INCOME_CLAIM_RISK"]
    decision = _evaluate(text, answer=answer)
    assert decision.allowed is False
    assert decision.provider == "risk_engine"


@pytest.mark.parametrize("text", LIVE_VARIANTS, ids=LIVE_VARIANT_IDS)
def test_every_live_variant_with_an_earnings_promise_is_refused(text) -> None:
    for promised in (text + "\n\n" + EARNINGS_PROMISE, EARNINGS_PROMISE + "\n\n" + text):
        assert [issue.code for issue in IncomeClaimPolicy().evaluate(_context(promised))] == ["INCOME_CLAIM_RISK"]
        for answer in (False, True):
            assert _evaluate(promised, answer=answer).allowed is False
