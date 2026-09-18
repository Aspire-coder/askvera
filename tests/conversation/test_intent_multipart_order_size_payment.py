"""MULTIPART-001 (regression pack, tests/conversation_pack/cases.json, Lane G). Deterministic/local proof:
"What is the minimum order for an FBO in Kenya, and what payment methods do
they accept?" lost the payment-methods sentence.

Reproduced (2026-09-18): remove_unrequested_directory_fields's dedicated
minimum-order-question branch (utils/directory_fields.py, ~line 664) matches
this question ("minimum ... order"), and then unconditionally stripped every
payment/delivery/hours sentence from the answer without checking whether the
SAME question also asked for one of those fields - so the correctly-generated
two-part answer's payment-methods sentence was deleted along with the
minimum-order answer's usual unrelated prose.

Fix: reuse the module's existing requested-field detection
(_requested_directory_field_set, built from the same per-field regexes
_requested_directory_field_set already uses elsewhere in this module - see
utils/directory_fields.py:675, :361, :435) to exclude any field the question
itself names from the strip pattern. No new phrases were added.

Multilingual update (Phase 2 / Lane B, 2026-09-18): the gap this docstring
used to describe - _requested_directory_field_set and the order-size trigger
regex both being English-only, so a French equivalent of this same two-part
question fell through to the "not confidently understood" path and left the
answer untouched (safe, but not because of any localized field detection) -
is now closed for French (and nine other languages) by
config/directory_field_vocabulary.py plus the ``language`` keyword added to
remove_unrequested_directory_fields/_requested_directory_field_set. See
tests/conversation/test_multilingual_fields.py for the full per-language
positive/negative matrix. test_french_equivalent_multipart_question_is_kept_in_full
below replaces the old "documents the gap, answer untouched" assertion with
a real positive one (both halves survive, `changed is False`) - the one
existing assertion in this file this project is allowed to strengthen rather
than leave as a pinned gap.
"""

from __future__ import annotations

from utils.directory_fields import remove_unrequested_directory_fields

KENYA_ANSWER = (
    "Minimum order size FBO: $100 worth of products when joining, $50 of products after joining.\n"
    "Payment methods accepted: Bank deposit, Credit Card, Mobile Money Transfer (Mpesa)."
)
MULTIPART_QUESTION = "What is the minimum order for an FBO in Kenya, and what payment methods do they accept?"


def test_multipart_001_keeps_both_requested_fields() -> None:
    """The regression-pack case: both halves of the question must survive."""
    result, changed = remove_unrequested_directory_fields(KENYA_ANSWER, MULTIPART_QUESTION)
    assert "$100 worth of products when joining" in result
    assert "Mpesa" in result
    assert changed is False


def test_order_size_and_delivery_time_two_part_question_keeps_both() -> None:
    """A different pair of requested fields on the same branch, to show the
    fix generalizes rather than special-casing payment methods."""
    answer = (
        "Minimum order size FBO: $100 worth of products when joining.\n"
        "Average Lead Time: 5 business days."
    )
    question = "What is the minimum order size for an FBO, and what is the average delivery time?"
    result, changed = remove_unrequested_directory_fields(answer, question)
    assert "$100 worth of products when joining" in result
    assert "5 business days" in result
    assert changed is False


def test_order_size_only_question_still_sheds_unrelated_payment_and_delivery_prose() -> None:
    """Negative control / existing-behaviour pin: an order-size-ONLY question
    must keep shedding unrelated payment/delivery/hours prose exactly as
    before this fix - see also
    test_focus_minimum_order_answer_removes_payment_and_delivery_claims in
    tests/unit/test_directory_fields.py."""
    answer = "Payment methods accepted are Bank Transfer, Cash, and there is no delivery charge."
    result, changed = remove_unrequested_directory_fields(answer, "what is the minimum order size for Niger")
    assert result == ""
    assert changed is True


def test_order_size_and_hours_two_part_question_keeps_hours_and_sheds_payment() -> None:
    """Only the field actually asked for is protected - an unrequested third
    field on the same branch is still removed."""
    answer = (
        "Minimum order size FBO: $100 worth of products when joining.\n"
        "Business Hours: 08:00 am - 17:00 pm.\n"
        "Payment methods accepted: Bank deposit, Cash."
    )
    question = "What is the minimum order size for an FBO, and what are the business hours?"
    result, changed = remove_unrequested_directory_fields(answer, question)
    assert "08:00 am" in result
    assert "Payment methods accepted" not in result
    assert changed is True


def test_french_equivalent_multipart_question_is_kept_in_full() -> None:
    """The gap this test used to pin is closed: with language="fr", the
    localized order-size trigger and the French field-request vocabulary
    (config/directory_field_vocabulary.py) both fire, and both requested
    halves survive - the same real assertion
    test_multipart_001_keeps_both_requested_fields makes for English, not
    merely "left untouched"."""
    question_fr = (
        "Quelle est la commande minimum pour un FBO au Kenya, "
        "et quels moyens de paiement acceptent-ils ?"
    )
    result, changed = remove_unrequested_directory_fields(KENYA_ANSWER, question_fr, language="fr")
    assert "$100 worth of products when joining" in result
    assert "Mpesa" in result
    assert changed is False
