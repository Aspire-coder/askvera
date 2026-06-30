"""Unit tests for local guardrail denied-topic checks."""

import pytest

from services.guardrails import check_text
from utils.exceptions import GuardrailBlockedError


def test_income_claim_is_blocked() -> None:
    """Income guarantees are blocked before Bedrock."""
    with pytest.raises(GuardrailBlockedError):
        check_text("Can I get rich with guaranteed income?", "cid")


def test_normal_policy_question_passes() -> None:
    """Allowed questions do not raise."""
    check_text("What is the return policy?", "cid")
