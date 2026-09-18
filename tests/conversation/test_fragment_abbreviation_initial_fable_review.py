"""Fragment audit (Phase 2, Lane D), Fable Phase 2 review correction, finding 4:
a correct short neighbour sentence was merged into whatever
`remove_unsupported_numeric_sentences` deleted after it, because
`utils.sentence_spans.abbreviation_or_initial_before` treated ANY bare
capital-letter-plus-dot as an initial, regardless of what followed it, and
treated a plain abbreviation as non-terminal even when an uppercase word
followed. Deterministic/local: pure function calls against
`RetrievedDocument` stubs, no model or network call.

Companion to tests/conversation/test_fragment_numeric_repair_abbreviations.py
(round 2's approx./Nr./J. R. Smith fixes, which must keep passing unchanged -
see that file's own docstring). This file adds the round-3 (Fable review)
repros: a lone initial ("C.", "A.") and a plain abbreviation before an
uppercase word ("No.", "Dec.") must NOT swallow the sentence after them.
"""

from __future__ import annotations

from app.retrieval.models import RetrievedDocument
from app.validation.validators.numeric_grounding_validator import remove_unsupported_numeric_sentences


def _document(content: str) -> RetrievedDocument:
    return RetrievedDocument(id="d1", title="t", content=content, source="s", score=1.0, metadata={})


def test_no_before_an_uppercase_word_does_not_swallow_the_deleted_sentence() -> None:
    """Before the fix: "no" is a plain abbreviation, unconditionally treated as
    non-terminal, so "Is the fee refundable? No. Delivery takes 5 days."
    read as ONE unit spanning "No." through "5 days.", and deleting the
    unsupported "5" took "No." down with it, leaving only "Is the fee
    refundable?" - the correct "No." answer was lost. After the fix: a plain
    abbreviation is non-terminal only before a digit or lowercase letter, so
    "No." (before uppercase "Delivery") is read as its own sentence and
    survives."""
    answer = "Is the fee refundable? No. Delivery takes 5 days."
    repaired, removed = remove_unsupported_numeric_sentences(
        answer, [_document("Refunds are not offered under this policy.")]
    )
    assert removed == ["5"]
    assert repaired == "Is the fee refundable? No."


def test_lone_initial_vitamin_c_does_not_swallow_the_deleted_sentence() -> None:
    """A single "C." with no second initial nearby is an ordinary sentence end,
    not an initial - before the fix, the old blanket single-letter rule
    treated it as one, merging "Take Vitamin C." into the deleted "5 days"
    sentence and leaving only "Take Vitamin" (or worse) once the number was
    removed."""
    answer = "Take Vitamin C. Delivery takes 5 days."
    repaired, removed = remove_unsupported_numeric_sentences(
        answer, [_document("Vitamins are recommended for general health.")]
    )
    assert removed == ["5"]
    assert repaired == "Take Vitamin C."


def test_lone_initial_form_a_does_not_swallow_the_deleted_sentence() -> None:
    answer = "Use Form A. Delivery takes 5 days."
    repaired, removed = remove_unsupported_numeric_sentences(
        answer, [_document("Form A must be completed for registration.")]
    )
    assert removed == ["5"]
    assert repaired == "Use Form A."


def test_month_abbreviation_before_uppercase_does_not_swallow_the_deleted_sentence() -> None:
    """"Dec." (a plain abbreviation) before the uppercase "Delivery" is a real
    sentence end, per the same rule as "No." above."""
    answer = "Send it by Dec. Delivery takes 5 days."
    repaired, removed = remove_unsupported_numeric_sentences(
        answer, [_document("Packages must be sent by December for the holiday schedule.")]
    )
    assert removed == ["5"]
    assert repaired == "Send it by Dec."


def test_negative_control_round_2_abbreviations_still_protected() -> None:
    """Positive control: this file's stricter rule must not regress round 2's
    fixes for "approx." (still non-terminal, because a DIGIT follows)."""
    answer = "The fee is approx. 999 USD for this tier. Payment methods accepted: cash."
    repaired, removed = remove_unsupported_numeric_sentences(
        answer, [_document("Payment methods accepted: cash.")]
    )
    assert removed == ["999"]
    assert repaired == "Payment methods accepted: cash."


def test_negative_control_initial_chain_still_protected() -> None:
    """Positive control: a genuine chain of two or more initials ("J. R.") is
    still read as one unit, unlike the lone "C."/"A." cases above."""
    answer = "Contact J. R. Smith about the 999 USD fee. Payment methods accepted: cash."
    repaired, removed = remove_unsupported_numeric_sentences(
        answer, [_document("Payment methods accepted: cash.")]
    )
    assert removed == ["999"]
    assert repaired == "Payment methods accepted: cash."
