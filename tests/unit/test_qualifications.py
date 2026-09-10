"""Conditions attached to a figure, and whether an answer kept them.

A minimum order stated without "for Preferred Customers" is not a shorter
answer. It is a different rule, told to the wrong person, in a voice that
invites no checking.

The corpus sentences here are verbatim.
"""

from __future__ import annotations

import pytest

from utils.qualifications import (
    answer_keeps_every_condition,
    misattached_figures,
    missing_qualifications,
    qualifying_clauses,
    value_is_conveyed,
)

ALGERIA_VALUE = (
    "0,200CC as a first order for Preferred Customers, 7 800DZD ($60) and the "
    "equivalent of 5 000 DZD ($43) after the first purchase for all FBOs"
)
FRANCE_VALUE = (
    "We do not have a minimum order in France, yet a newly sponsored Preferred "
    "Customer will have to order 150€ minimum of products within 72 hours in "
    "order to validate his sponsorship"
)


# --- what counts as a condition ---------------------------------------------


def test_a_role_condition_is_found() -> None:
    assert "as a first order for Preferred Customers" in qualifying_clauses(ALGERIA_VALUE)


def test_a_timing_condition_is_found() -> None:
    assert "after the first purchase for all FBOs" in qualifying_clauses(ALGERIA_VALUE)


def test_an_eligibility_condition_is_found() -> None:
    assert "within 72 hours in order to validate his sponsorship" in qualifying_clauses(
        FRANCE_VALUE
    )


@pytest.mark.parametrize(
    "value",
    [
        "0,200CC (7 800DZD)",
        "2 CC",
        "€81",
        "",
    ],
)
def test_a_bare_figure_has_no_conditions(value: str) -> None:
    """Nothing is invented. A value with no condition must not acquire one."""
    assert qualifying_clauses(value) == []


def test_a_phrase_too_short_to_be_a_condition_is_not_one() -> None:
    """"per order" restates the field's own subject and narrows nothing."""
    assert qualifying_clauses("2 CC per order") == []


# --- which conditions an answer dropped -------------------------------------


def test_an_answer_stating_only_the_figure_is_missing_both_conditions() -> None:
    missing = missing_qualifications("The minimum order size is 0,200CC.", ALGERIA_VALUE)

    assert missing == [
        "as a first order for Preferred Customers",
        "after the first purchase for all FBOs",
    ]


def test_the_france_answer_a_reader_received_is_missing_its_condition() -> None:
    """Delivered in the pilot. True as far as it goes, and it does not go far enough."""
    answer = "For an FBO in France, there is no minimum order requirement."

    assert missing_qualifications(answer, FRANCE_VALUE) == [
        "within 72 hours in order to validate his sponsorship"
    ]


def test_a_rephrased_condition_still_counts_as_kept() -> None:
    """Matching the words, not the string - an answer may reorder around it."""
    answer = (
        "Preferred Customers must place a first order of 0,200CC. After the first "
        "purchase, all FBOs order 7 800DZD."
    )

    assert missing_qualifications(answer, ALGERIA_VALUE) == []
    assert answer_keeps_every_condition(answer, ALGERIA_VALUE) is True


def test_an_empty_answer_is_missing_everything() -> None:
    assert missing_qualifications("", ALGERIA_VALUE) == qualifying_clauses(ALGERIA_VALUE)


# --- whether the figures themselves came through ----------------------------


def test_a_reordered_answer_still_conveys_the_value() -> None:
    """The substring test called this incomplete and appended the field twice."""
    value = "2 CC as a first order for Preferred Customers"
    answer = "As a first order for Preferred Customers the minimum order size is 2 CC."

    assert value_is_conveyed(answer, value) is True
    assert missing_qualifications(answer, value) == []


def test_covering_the_words_is_not_stating_the_figure() -> None:
    """The Niger case: the capture ran into the next field.

    An answer that lists the payment methods uses every word of that captured
    value while never mentioning 81, which is the only thing the field is
    about.
    """
    value = "€81. Payment methods accepted: Bank Transfer, Cash"
    answer = "Payment methods accepted are Bank Transfer, Cash, and there is no delivery charge."

    assert value_is_conveyed(answer, value) is False


def test_separator_differences_do_not_hide_a_stated_figure() -> None:
    """A source writing "7 800DZD" and an answer writing "7800 DZD" agree."""
    assert value_is_conveyed("The minimum is 7800 DZD.", "7 800DZD") is True


def test_a_decimal_figure_is_matched_across_notations() -> None:
    assert value_is_conveyed("The first order is 0.200 CC.", "0,200CC") is True


# --- the multiline, bulleted and adjacent-field shapes the corpus uses ------


def test_a_condition_wrapped_across_lines_is_still_one_condition() -> None:
    """The PDF wraps mid-field; the condition does not stop at the newline."""
    value = "150€ minimum of products within 72 hours in order\nto validate his sponsorship"

    assert qualifying_clauses(value) == [
        "within 72 hours in order to validate his sponsorship"
    ]


def test_an_abbreviation_inside_a_value_does_not_split_a_condition() -> None:
    value = "2 CC (Ref. 830) for all newly sponsored FBOs"

    assert qualifying_clauses(value) == ["for all newly sponsored FBOs"]


def test_conditions_are_returned_in_the_order_the_source_wrote_them() -> None:
    """So a caller restoring them cannot reorder a policy."""
    assert qualifying_clauses(ALGERIA_VALUE) == [
        "as a first order for Preferred Customers",
        "after the first purchase for all FBOs",
    ]


# --- the limit, asserted rather than left to be discovered ------------------


def test_an_unrecognised_phrasing_is_missed_and_that_is_the_safe_direction() -> None:
    """Recorded as a known limit.

    A condition phrased without one of the recognised openers is not found, so
    the answer is judged complete when it is not. That leaves current
    behaviour. The other kind of mistake - inventing a condition - would put
    text in front of a reader that no source supports.
    """
    value = "2 CC, Preferred Customers excluded from this figure"

    assert qualifying_clauses(value) == []


# --- the figure must reach the right people ---------------------------------
#
# Stating the figure and stating the condition is still not enough. An answer
# can mention Preferred Customers somewhere, quote 0,200CC, and hand that
# figure to FBOs: every word present, every word in the wrong place.


def test_a_figure_attached_to_the_wrong_category_is_reported() -> None:
    """The case word coverage cannot see.

    Both conditions are word-for-word present, so `missing_qualifications` is
    satisfied, and the reader has still been given a number that is not theirs.
    """
    answer = (
        "As an FBO you order 0,200CC as a first order. Preferred Customers are "
        "covered separately. After the first purchase all FBOs order 7 800DZD."
    )

    assert missing_qualifications(answer, ALGERIA_VALUE) == []
    assert misattached_figures(answer, ALGERIA_VALUE) == ["0200"]


def test_a_figure_attached_to_the_right_category_is_not_reported() -> None:
    answer = (
        "As a Preferred Customer you order 0,200CC as a first order. After the "
        "first purchase all FBOs order 7 800DZD."
    )

    assert misattached_figures(answer, ALGERIA_VALUE) == []
    assert missing_qualifications(answer, ALGERIA_VALUE) == []


def test_a_figure_named_without_a_category_is_not_a_mismatch() -> None:
    """Only a genuine disagreement counts.

    An answer that names no category has dropped the condition, which is the
    other check's question. Reporting it here too would say the same defect
    twice and hide the difference between the two.
    """
    answer = "The first order minimum is 0,200CC and after that it is 7 800DZD."

    assert misattached_figures(answer, ALGERIA_VALUE) == []
    assert missing_qualifications(answer, ALGERIA_VALUE)


def test_a_decimal_comma_is_not_a_clause_boundary() -> None:
    """The defect that made this check report exactly backwards.

    Splitting "0,200CC as a first order for Preferred Customers" at the decimal
    comma attached "200" to the condition and left "0" bare, so a correct
    answer was flagged and an incorrect one was not.
    """
    from utils.qualifications import _segments

    segments = _segments(ALGERIA_VALUE)

    assert any("0,200CC" in segment for segment in segments)
    assert not any(segment.strip() == "0" for segment in segments)


def test_a_sentence_boundary_separates_categories() -> None:
    """Without it, two sentences naming two categories read as one clause."""
    from utils.qualifications import _segments

    segments = _segments("As an FBO you order 2 CC. Preferred Customers order 1 CC.")

    assert len(segments) == 2


def test_singular_and_plural_are_the_same_condition() -> None:
    """A source writing "Customers" and an answer writing "Customer" agree."""
    answer = "As a Preferred Customer, the first order is 2 CC."

    assert missing_qualifications(answer, "2 CC as a first order for Preferred Customers") == []
