"""Order-size answers keep what was asked for and nothing else. Mocked/local behaviour.

Deterministic post-processing (utils.directory_fields), with no model involved.
The first two cases are the independent reviewer's reproductions against the
MULTIPART-001 fix (Fable review, 2026-09-18).
"""

from __future__ import annotations

import pytest

from utils.directory_fields import remove_unrequested_directory_fields

ANSWER = (
    "Minimum order size FBO: $100 worth of products when joining. "
    "Business hours are 09.00 am - 19.00 pm. "
    "Payment methods accepted: Mpesa."
)
ORDER = "Minimum order size FBO: $100 worth of products when joining."
HOURS = "Business hours are 09.00 am - 19.00 pm."
PAYMENT = "Payment methods accepted: Mpesa."


@pytest.mark.parametrize(
    "question",
    [
        "What is the minimum order size for an FBO if I need it delivered within 48 hours?",
        "What is the minimum order size for an FBO? I only have 2 hours to decide.",
    ],
)
def test_a_duration_in_hours_is_not_a_request_for_business_hours(question: str) -> None:
    kept, _ = remove_unrequested_directory_fields(ANSWER, question)
    assert kept == ORDER


def test_explicit_office_hours_are_kept_alongside_the_order_size() -> None:
    kept, _ = remove_unrequested_directory_fields(ANSWER, "What is the minimum order size and the office hours?")
    assert kept == f"{ORDER} {HOURS}"


def test_requested_payment_methods_are_kept_alongside_the_order_size() -> None:
    kept, _ = remove_unrequested_directory_fields(
        ANSWER, "What is the minimum order and what payment methods do they accept?"
    )
    assert kept == f"{ORDER} {PAYMENT}"


def test_order_size_only_question_sheds_every_other_field() -> None:
    kept, changed = remove_unrequested_directory_fields(ANSWER, "What is the minimum order size in Kenya?")
    assert kept == ORDER
    assert changed is True


def test_a_decimal_time_is_removed_whole_not_split_at_its_dot() -> None:
    """Before: the sentence ended at the "." inside "09.00", leaving "00 am - 19.00 pm."."""
    kept, _ = remove_unrequested_directory_fields(ANSWER, "What is the minimum order size in Kenya?")
    assert "00 am" not in kept
    assert "19.00" not in kept
