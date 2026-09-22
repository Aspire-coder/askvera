"""Fragment audit (Phase 2, Lane D): abbreviation- and initial-triggered fragments
left by ``remove_unsupported_numeric_sentences``. Deterministic/local: pure
function calls against ``RetrievedDocument`` stubs, no model or network call.

``remove_unsupported_numeric_sentences``
(``app/validation/validators/numeric_grounding_validator.py``) used to find
sentence boundaries with a bare ``[.!?](?=\\s|$)`` search, guarded only
against a letter-dot-letter-dot run such as "e.g." or "U.S." (two or more
repeats). A single abbreviation like "approx.", "ca." or "Nr.", or an
initial like "J.", is not that shape, so the period after it was read as the
end of the sentence. When the unsupported number that followed was removed,
the abbreviation was left standing alone as the "sentence" before it - the
same defect class as the already-fixed "09.00" decimal-time fragment
(tracker: MULTIPART-001 / Fable review 2026-09-18), reproduced here on
abbreviations instead of decimals.

Fixed (Phase 2 Lane D, round 2, 2026-09-18) by adding
``utils.sentence_spans.abbreviation_or_initial_before`` as an extra guard on
the same boundary regex, rather than by swapping in
``utils.sentence_spans.sentence_boundaries`` wholesale: that fuller boundary
rule also requires an uppercase letter, opening quote, line break or end of
text to follow before it calls anything a boundary, which reads "You must
generate 120 Open Group Case Credits. (There is an exception ..." as one
sentence (since "(" is not uppercase/quote/newline) and deletes the grounded
"120" sentence along with the exception clause that follows it - this was
round 1's patch, and it broke
``tests/unit/test_numeric_grounding_validator.py::
test_repair_does_not_orphan_a_bracket_and_break_the_answer``.
``abbreviation_or_initial_before`` answers only "is this period abbreviation
punctuation", leaving what follows to this function's own boundary regex, so
that case is untouched.
"""

from __future__ import annotations

from app.retrieval.models import RetrievedDocument
from app.validation.validators.numeric_grounding_validator import remove_unsupported_numeric_sentences


def _document(content: str) -> RetrievedDocument:
    return RetrievedDocument(
        id="d1", title="t", content=content, source="s", score=1.0, metadata={}
    )


def test_removing_an_unsupported_figure_after_approx_does_not_orphan_the_abbreviation() -> None:
    answer = "The fee is approx. 999 USD for this tier. Payment methods accepted: cash."
    repaired, removed = remove_unsupported_numeric_sentences(
        answer, [_document("Payment methods accepted: cash.")]
    )
    assert removed == ["999"]
    # Before the fix: "The fee is approx. Payment methods accepted: cash." -
    # a dangling "approx." with nothing after it. The whole first sentence,
    # abbreviation included, must go with the number it introduced.
    assert "approx." not in repaired
    assert repaired == "Payment methods accepted: cash."


def test_removing_an_unsupported_figure_after_nr_does_not_orphan_the_abbreviation() -> None:
    answer = "See policy Nr. 999 for the fee schedule. Payment methods accepted: cash."
    repaired, removed = remove_unsupported_numeric_sentences(
        answer, [_document("Payment methods accepted: cash.")]
    )
    assert removed == ["999"]
    assert repaired == "Payment methods accepted: cash."


def test_removing_an_unsupported_figure_after_initials_does_not_orphan_the_name() -> None:
    answer = "Contact J. R. Smith about the 999 USD fee. Payment methods accepted: cash."
    repaired, removed = remove_unsupported_numeric_sentences(
        answer, [_document("Payment methods accepted: cash.")]
    )
    assert removed == ["999"]
    # Before the fix: "Contact J. R. Payment methods accepted: cash." - the
    # name is severed from the sentence that named it.
    assert "Contact J. R." not in repaired
    assert repaired == "Payment methods accepted: cash."


def test_negative_control_a_grounded_neighbour_sentence_survives_untouched() -> None:
    """The correct neighbouring sentence, unrelated to the abbreviation, is kept whole."""
    answer = "The fee is approx. 999 USD for this tier. Payment methods accepted: cash."
    repaired, removed = remove_unsupported_numeric_sentences(
        answer, [_document("Payment methods accepted: cash.")]
    )
    assert repaired.endswith("Payment methods accepted: cash.")


def test_negative_control_a_legitimate_sentence_break_still_removes_cleanly() -> None:
    """No abbreviation involved: the existing behaviour (whole-sentence removal) is unaffected."""
    answer = "The minimum order is 999 USD. Payment methods accepted: cash."
    repaired, removed = remove_unsupported_numeric_sentences(
        answer, [_document("Payment methods accepted: cash.")]
    )
    assert removed == ["999"]
    assert repaired == "Payment methods accepted: cash."


def test_negative_control_a_short_word_that_only_looks_like_an_abbreviation_still_splits() -> None:
    """"ok." is abbreviation-shaped (short word plus a period) but is not a known
    abbreviation, so the sentence it ends is still removed as its own unit,
    exactly as a genuine sentence break is - unlike "approx." above, whose
    word is on the known list."""
    answer = "That is ok. The fee is 999 USD for this tier. Payment methods accepted: cash."
    repaired, removed = remove_unsupported_numeric_sentences(
        answer, [_document("That is ok. Payment methods accepted: cash.")]
    )
    assert removed == ["999"]
    assert repaired == "That is ok. Payment methods accepted: cash."


def test_negative_control_a_decimal_number_does_not_split() -> None:
    """The point inside a decimal is never read as a sentence end."""
    answer = "The fee is 99.50 USD for this tier. Payment methods accepted: cash."
    repaired, removed = remove_unsupported_numeric_sentences(
        answer, [_document("Payment methods accepted: cash.")]
    )
    assert removed == ["99.50"]
    assert repaired == "Payment methods accepted: cash."


def test_negative_control_an_email_address_does_not_split() -> None:
    """The dots inside an email address are never read as sentence ends, so an
    unsupported number in a different sentence does not cut the address in half."""
    answer = "Contact support@example.com for help. The fee is 999 USD for this tier."
    repaired, removed = remove_unsupported_numeric_sentences(
        answer, [_document("Contact support@example.com for help.")]
    )
    assert removed == ["999"]
    assert repaired == "Contact support@example.com for help."


def test_negative_control_a_clause_reference_does_not_split() -> None:
    """A clause reference such as "16.02(k)." keeps its digit-grouped dots and its
    closing bracket intact; only the sentence with the unsupported number goes."""
    answer = "See clause 16.02(k). The fee is 999 USD for this tier. Payment methods accepted: cash."
    repaired, removed = remove_unsupported_numeric_sentences(
        answer, [_document("See clause 16.02(k). Payment methods accepted: cash.")]
    )
    assert removed == ["999"]
    assert repaired == "See clause 16.02(k). Payment methods accepted: cash."
