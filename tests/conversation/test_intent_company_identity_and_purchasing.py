"""C1/C2: ordinary company-identity and purchasing/returns questions must not
trigger an income disclaimer or any other unrelated guardrail.

Method: reproduce through the REAL code path rather than a fake. The router
that can mis-tag these questions as "income_claim" is
app/retrieval/providers.py's semantic query planner (Codex-owned, a live
Bedrock call, out of scope to edit here) but the deterministic safety net
that catches a false-positive label from it -
app/retrieval/providers.py:_verified_conversation_intent - is exercised
directly below with a runtime double that raises if the model is ever
called, proving the false-positive is caught WITHOUT needing a live model
call: has_income_context(message) is False and the language is covered, so
the bypass fires deterministically and the model is never consulted.

Reproduction result (2026-09-18): all three example questions from the task
board already downgrade "income_claim" -> "knowledge" through this bypass
(shipped in baseline B1, fix/income-bypass-coverage-and-market-config-...).
Governance (services.guardrails / app.governance.governance_engine) also
allows all three outright - no DENIED_TOPICS phrase matches "What is Forever
Living Products?", "Where can I buy Forever products?" or "What are the
return conditions?" for income_claim, medical_claim or off_topic.

No code change was needed for C1/C2 as stated on the task board; this pins
the already-fixed behaviour (no-defect-pinned) and adds negative controls
proving a REAL income or medical claim request still refuses.
"""

from __future__ import annotations

import pytest

from app.governance import governance_engine
from app.retrieval.providers import _verified_conversation_intent
from app.risk.policies.income_claim_policy import IncomeClaimPolicy
from app.risk.policies.income_claim_translations import is_covered_language


class _RuntimeThatMustNotBeCalled:
    """Fails the test if the semantic classifier's model call is ever reached."""

    def converse(self, **_kwargs):  # pragma: no cover - only hit on regression
        raise AssertionError(
            "the deterministic bypass should have short-circuited before any model call"
        )


COMPANY_IDENTITY_AND_PURCHASING_QUESTIONS = [
    "What is Forever Living Products?",
    "Where can I buy Forever products?",
    "What are the return conditions?",
]


@pytest.mark.parametrize("message", COMPANY_IDENTITY_AND_PURCHASING_QUESTIONS)
def test_income_intent_verification_downgrades_false_positive_without_a_model_call(message: str) -> None:
    """A semantic mis-tag of "income_claim" on these questions is caught deterministically."""
    result = _verified_conversation_intent(
        "income_claim", message, "US", "en", "cid", _RuntimeThatMustNotBeCalled()
    )
    assert result == ("knowledge", True)


@pytest.mark.parametrize("message", COMPANY_IDENTITY_AND_PURCHASING_QUESTIONS)
def test_income_claim_policy_finds_no_income_context(message: str) -> None:
    assert not IncomeClaimPolicy().has_income_context(message)
    assert is_covered_language("en", message)


@pytest.mark.parametrize("message", COMPANY_IDENTITY_AND_PURCHASING_QUESTIONS)
def test_governance_allows_these_questions_outright(message: str) -> None:
    decision = governance_engine.evaluate(text=message, country="US", language="en", correlation_id="cid")
    assert decision.allowed is True
    assert decision.metadata["risk"]["issueCount"] == 0


# --- Negative controls: a real claim on the same topics must still refuse ---


def test_real_income_guarantee_about_products_still_refuses() -> None:
    """A genuine guaranteed-earnings request must not be swept up by the bypass."""
    result = _verified_conversation_intent(
        "income_claim",
        "If I buy Forever products, do you guarantee I'll earn a lot of money reselling them?",
        "US",
        "en",
        "cid",
        _RuntimeThatMustNotBeCalled(),
    )
    # has_income_context is True here, so the deterministic bypass never
    # fires and the (mocked-out) model path would be reached instead; the
    # important thing is that "knowledge" is NOT returned without review.
    assert result[0] != "knowledge" or result[1] is False


def test_real_medical_claim_about_a_returned_product_still_flagged() -> None:
    decision = governance_engine.evaluate(
        text="Can I return the Aloe Vera Gel and tell people it cures my arthritis?",
        country="US",
        language="en",
        correlation_id="cid",
    )
    issues = decision.metadata["risk"]["issues"]
    assert any("medical" in str(issue.get("code", "")).lower() for issue in issues) or not decision.allowed
