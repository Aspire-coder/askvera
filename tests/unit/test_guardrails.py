"""Unit tests for local guardrail denied-topic checks."""

import pytest

from services.guardrails import check_text
from utils.exceptions import GuardrailBlockedError


def test_income_claim_is_blocked() -> None:
    """Income guarantees are blocked before Bedrock."""
    with pytest.raises(GuardrailBlockedError) as exc_info:
        check_text("Can I get rich with guaranteed income?", "cid")

    assert exc_info.value.topic == "income_claim"


def test_medical_claim_is_blocked_with_correct_topic() -> None:
    with pytest.raises(GuardrailBlockedError) as exc_info:
        check_text("Will Forever Aloe help with arthritis?", "cid")

    assert exc_info.value.topic == "medical_claim"


def test_off_topic_request_is_blocked_with_correct_topic() -> None:
    with pytest.raises(GuardrailBlockedError) as exc_info:
        check_text("Can you give me advice about gambling?", "cid")

    assert exc_info.value.topic == "off_topic"


def test_normal_policy_question_passes() -> None:
    """Allowed questions do not raise."""
    check_text("What is the return policy?", "cid")
