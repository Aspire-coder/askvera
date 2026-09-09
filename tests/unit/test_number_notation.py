"""Reading a figure the way its document meant it, or admitting we cannot.

The corpus excerpts here are verbatim - reformatting them would remove the
thing being tested. They come from the same dump as
`tests/unit/test_numeric_notation_coverage.py`.

The case that matters most is the one that returns nothing: "1,612CC" is 1612
to an English reader and 1.612 to a French one, and a module that picks is
wrong half the time invisibly. Several tests below exist only to assert that it
does not pick.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from utils.number_notation import (
    document_decimal_separator,
    read_number,
    readings_in,
)

# Verbatim, from askvera-policy-sections. Note the spaces inside "7 800" and
# "5 000" - those are group separators, not word breaks.
ALGERIA = (
    "Minimum order size FBO: 0,200CC as a first order for Preferred Customers, "
    "7 800DZD ($60) and the equivalent of 5 000 DZD ($43) after the first purchase."
)


# --- what the source wrote is never lost ------------------------------------


def test_a_reading_keeps_the_text_exactly_as_written() -> None:
    """The original string is evidence and is never normalised away."""
    reading = read_number("0,200CC", document_text=ALGERIA)

    assert reading.text == "0,200"
    assert reading.value == Decimal("0.200")
    assert reading.unit == "CC"
    assert reading.resolved is True


def test_every_reading_carries_its_reason() -> None:
    """A value without its justification is an assertion, not a reading."""
    for reading in readings_in(ALGERIA, document_text=ALGERIA):
        assert reading.evidence
        assert reading.evidence != ""


def test_the_unit_comes_from_the_source_not_from_the_market() -> None:
    readings = {reading.text: reading.unit for reading in readings_in(ALGERIA, document_text=ALGERIA)}

    assert readings["0,200"] == "CC"
    assert readings["7 800"] == "DZD"
    assert readings["60"] == "$"


# --- decimal commas, decimal points, thousands separators -------------------


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("7,5 EUR", Decimal("7.5")),
        ("$7.50", Decimal("7.50")),
        ("0,200CC", Decimal("0.200")),
        ("0.200CC", Decimal("0.200")),
        ("60", Decimal("60")),
    ],
)
def test_a_separator_that_cannot_be_a_thousands_group_is_a_decimal(
    written: str, expected: Decimal
) -> None:
    """Not three digits after it, or a leading zero before it."""
    reading = read_number(written)

    assert reading.resolved is True
    assert reading.value == expected


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("7 800DZD", Decimal("7800")),
        ("5 000 DZD", Decimal("5000")),
        ("1 612 500", Decimal("1612500")),
    ],
)
def test_a_space_always_groups_digits(written: str, expected: Decimal) -> None:
    """No locale writes a decimal after a space."""
    reading = read_number(written)

    assert reading.resolved is True
    assert reading.value == expected


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("1,612.50 EUR", Decimal("1612.50")),
        ("1.612,50 EUR", Decimal("1612.50")),
        ("1 612,50 EUR", Decimal("1612.50")),
        ("1,612,500", Decimal("1612500")),
    ],
)
def test_two_separators_fix_each_other(written: str, expected: Decimal) -> None:
    """The later separator takes the decimal part; the earlier ones group."""
    reading = read_number(written)

    assert reading.resolved is True
    assert reading.value == expected


# --- the ambiguous shape stays unresolved -----------------------------------


@pytest.mark.parametrize("written", ["1,612", "1.612", "12,500", "3.000"])
def test_one_separator_with_three_digits_after_it_is_not_guessed(written: str) -> None:
    """The whole point. This shape means two different things and we cannot see which."""
    reading = read_number(written)

    assert reading.resolved is False
    assert reading.value is None
    assert reading.text == written
    assert "unresolved rather than guessed" in reading.evidence


def test_an_unresolved_reading_is_not_zero_and_not_absent() -> None:
    """Guarding the one way a caller could misread this: None is not 0."""
    reading = read_number("1,612CC")

    assert reading.value is None
    assert reading.value != Decimal("0")
    assert reading.text == "1,612"
    assert reading.unit == "CC"


# --- the document, not the country, resolves the ambiguity ------------------


def test_a_comma_decimal_document_resolves_its_own_ambiguous_figures() -> None:
    """The France defect, fixed generally.

    Nothing here knows the record is French. "0,200CC" in the same document is
    what decides it - a comma cannot be a thousands group after a lone zero.
    """
    document = "Minimum order size FBO: 1,612CC. Support fee 0,200CC per month."

    reading = read_number("1,612CC", document_text=document)

    assert reading.resolved is True
    assert reading.value == Decimal("1.612")
    assert "0,200" in reading.evidence


def test_a_dot_decimal_document_reads_the_same_figure_as_thousands() -> None:
    """The opposite reading of the same characters, from the opposite evidence.

    Same unit on both figures, which is what makes the evidence apply.
    """
    document = "Minimum order size FBO: 1,612 CC. The first order is 0.200 CC."

    reading = read_number("1,612 CC", document_text=document)

    assert reading.resolved is True
    assert reading.value == Decimal("1612")
    assert "0.200" in reading.evidence


# --- evidence does not carry across units -----------------------------------
#
# The weaker of the two assumptions, and the one that mattered. A dollar price
# follows the dollar's convention whatever language the record is written in.


@pytest.mark.parametrize(
    "document",
    [
        "Minimum order size FBO: 1,612CC. The support fee is 3.50 EUR.",
        "Minimum order size FBO: 1,612CC as a first order. Equivalent $7.50 per unit.",
        "Minimum order size FBO: 1,612CC. Delivery costs 7,5 DZD.",
    ],
)
def test_a_figure_in_another_unit_decides_that_unit_and_not_this_one(document: str) -> None:
    """"3.50 EUR" elsewhere does not establish that "1,612CC" means 1612."""
    reading = read_number("1,612CC", document_text=document)

    assert reading.resolved is False
    assert reading.value is None
    assert "another unit" in reading.evidence


def test_same_unit_evidence_still_resolves_inside_a_mixed_document() -> None:
    """Being strict about units must not stop the case this exists for.

    The Algeria record carries a dollar price beside a CC figure, and the CC
    figure is still decided - by the other CC figure.
    """
    document = (
        "Minimum order size FBO: 1,612CC as a first order, 0,200CC after the "
        "first purchase. Equivalent $7.50 per unit."
    )

    reading = read_number("1,612CC", document_text=document)

    assert reading.resolved is True
    assert reading.value == Decimal("1.612")


# --- a document is not assumed to agree with itself -------------------------


def test_a_document_writing_one_unit_both_ways_resolves_nothing() -> None:
    """Two deciding figures in the same unit pointing opposite ways.

    Nothing is wrong with such a record - it may have been assembled from two
    sources - but no convention can be read out of it, and picking the first
    found would spread that choice over every ambiguous figure in it.
    """
    document = (
        "Minimum order size FBO: 1,612CC. First order 0,200CC. Annual target 7.5CC."
    )

    separator, evidence = document_decimal_separator(document, "CC")

    assert separator is None
    assert "both ways" in evidence
    assert read_number("1,612CC", document_text=document).resolved is False


def test_an_unambiguous_figure_is_unaffected_by_a_conflict() -> None:
    """A figure that decides itself never consults the document at all."""
    document = "First order 0,200CC. Annual target 7.5CC. Delivery 7 800DZD."

    readings = {reading.text: reading for reading in readings_in(document, document_text=document)}

    assert readings["7 800"].resolved is True
    assert readings["7 800"].value == Decimal("7800")
    assert readings["0,200"].value == Decimal("0.200")
    assert readings["7.5"].value == Decimal("7.5")


def test_a_document_with_no_deciding_figure_resolves_nothing() -> None:
    """Every figure in it is the ambiguous shape, so no convention is established."""
    document = "Minimum order size FBO: 1,612 CC. The annual target is 12,500 CC."

    separator, evidence = document_decimal_separator(document, "CC")

    assert separator is None
    assert "no figures in CC that fixes" in evidence
    assert read_number("1,612 CC", document_text=document).resolved is False


def test_no_market_or_language_is_consulted() -> None:
    """A France-specific rule would be a rule about one record, not about notation.

    The same characters with the same evidence must read the same way whatever
    record they came from, so this asserts the signature carries no country and
    no language to consult.
    """
    import inspect

    for function in (read_number, readings_in, document_decimal_separator):
        parameters = set(inspect.signature(function).parameters)
        assert not parameters & {"country", "market", "language", "locale"}


# --- mixed-format documents -------------------------------------------------


def test_a_mixed_document_reads_each_figure_on_its_own_shape() -> None:
    """The corpus record: a decimal comma, spaced thousands and dollar amounts.

    The document convention is only consulted for figures that need it; a
    figure that decides itself is never overridden by it.
    """
    readings = {reading.text: reading for reading in readings_in(ALGERIA, document_text=ALGERIA)}

    assert readings["0,200"].value == Decimal("0.200")
    assert readings["7 800"].value == Decimal("7800")
    assert readings["5 000"].value == Decimal("5000")
    assert readings["60"].value == Decimal("60")
    assert all(reading.resolved for reading in readings.values())


def test_a_sentence_is_evidence_about_itself_when_nothing_else_is_given() -> None:
    """Passing no document falls back to the text, which is often enough."""
    assert read_number("0,200CC and 1,612CC").resolved is True

    both = readings_in("Minimum 1,612CC, first order 0,200CC")

    assert [reading.value for reading in both] == [Decimal("1.612"), Decimal("0.200")]


def test_reading_nothing_returns_an_unresolved_reading_not_an_error() -> None:
    reading = read_number("no figures here")

    assert reading.resolved is False
    assert reading.value is None
    assert readings_in("") == []


def test_same_unit_evidence_is_an_inference_not_a_proof() -> None:
    """The limitation, asserted so it cannot be quietly forgotten.

    Matching units narrows the evidence to figures likely written by the same
    hand. It does not prove they were. A record carrying two markets' CC
    figures written to different conventions resolves one from the other and is
    wrong, and nothing local can tell them apart - the corpus carries no
    provenance per figure.

    Recorded here rather than in prose alone, with the reading it produces, so
    the exposure is visible and measurable rather than argued about.
    """
    two_markets = (
        "Algeria minimum order 0,200CC as a first order. "
        "Partner market annual target 1,612CC."
    )

    reading = read_number("1,612CC", document_text=two_markets)

    assert reading.resolved is True
    assert reading.value == Decimal("1.612")
    assert "0,200" in reading.evidence, (
        "resolved from the other market's figure - the inference this cannot avoid"
    )
