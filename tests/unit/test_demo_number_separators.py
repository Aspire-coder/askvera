"""A thousands-grouped figure matches the same figure grouped another way.

Observed live on 2026-09-12 for "What is the delivery cost in Mali?". The
approved directory record states "2.000 francs CFA until the highway
(Maristes)", "3.000 francs CFA from Maristes to Thiaroye" and "4.000 francs
CFA around Petit Mbao, ...". The model wrote the correct schedule as "2,000",
"3,000" and "4,000", numeric repair found none of them in the source, and the
fee schedule was deleted from the delivered answer.

A point or comma before exactly three digits is read as a thousands group only
when the source itself settles it: the figure is an amount in a currency that is
never stated to three decimal places. Case Credit figures ("1.612CC") and the
three-decimal currencies ("9.440 TND") stay ambiguous and keep today's exact
matching.
"""

import pytest

from app.retrieval.models import RetrievedDocument
from app.validation.validators.numeric_grounding_validator import (
    numbers_present_in_sources,
    remove_unsupported_numeric_sentences,
)

MALI_SOURCE = (
    "Forever Mali\n"
    "• Delivery Cost: 2.000 francs CFA until the highway (Maristes), "
    "3.000 francs CFA from Maristes to Thiaroye, "
    "4.000 francs CFA around Petit Mbao, Keur Mbaye Fall, Keur Massar.\n"
    "• The minimum amount for a purchase after registering is 53.000 francs CFA."
)


def _document(content: str, title: str = "Forever Mali") -> RetrievedDocument:
    return RetrievedDocument(
        id="sponsoring-014-mali",
        title=title,
        content=content,
        source="directory://sponsoring-014-mali",
        page="1",
        metadata={},
    )


def _repair(answer: str, source: str, title: str = "Forever Mali") -> tuple[str, list[str]]:
    return remove_unsupported_numeric_sentences(answer, [_document(source, title)])


def _mali_answer(two: str, three: str, four: str) -> str:
    return (
        "The delivery cost in Mali is:\n"
        f"- **{two} francs CFA** until the highway (Maristes)\n"
        f"- **{three} francs CFA** from Maristes to Thiaroye\n"
        f"- **{four} francs CFA** around Petit Mbao, Keur Mbaye Fall, Keur Massar"
    )


# ---------------------------------------------------------------------------
# The live defect: dot-grouped source, other groupings in the answer.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "figures",
    [
        ("2.000", "3.000", "4.000"),  # the source's own grouping: kept before and after
        ("2,000", "3,000", "4,000"),  # the live answer
        ("2000", "3000", "4000"),
        ("2 000", "3 000", "4 000"),
    ],
)
def test_mali_delivery_schedule_survives_any_thousands_grouping(figures):
    answer = _mali_answer(*figures)

    repaired, removed = _repair(answer, MALI_SOURCE)

    assert removed == []
    assert repaired == answer


@pytest.mark.parametrize("figure", ["53,000", "53000", "53 000"])
def test_mali_minimum_purchase_survives_any_thousands_grouping(figure):
    answer = f"The minimum amount for a purchase after registering is {figure} francs CFA."

    repaired, removed = _repair(answer, MALI_SOURCE)

    assert removed == []
    assert repaired == answer


@pytest.mark.parametrize("figure", ["2,000", "2000", "2 000", "53,000", "3,000", "4 000"])
def test_presence_check_finds_the_dot_grouped_source_figure(figure):
    assert numbers_present_in_sources([figure], [_document(MALI_SOURCE)]) == {figure: True}


@pytest.mark.parametrize("figure", ["€5,000", "€5000", "€5 000"])
def test_euro_amount_grouped_with_a_point_in_the_source(figure):
    source = "Registration fee: €5.000 for a distributor kit."
    answer = f"The registration fee is {figure} for a distributor kit."

    repaired, removed = _repair(source=source, answer=answer, title="Forever Belgium")

    assert removed == []
    assert repaired == answer


# ---------------------------------------------------------------------------
# The reverse: the answer groups with a point, the source does not.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("source_figure", ["2,000", "2 000"])
def test_point_grouped_answer_matches_comma_or_space_grouped_source(source_figure):
    source = f"• Delivery Cost: {source_figure} francs CFA until the highway (Maristes)."
    answer = "The delivery cost is 2.000 francs CFA until the highway (Maristes)."

    repaired, removed = _repair(answer, source)

    assert removed == []
    assert repaired == answer
    assert numbers_present_in_sources(["2.000"], [_document(source)]) == {"2.000": True}


@pytest.mark.parametrize(
    ("source_figure", "answer_figure"),
    [
        ("20 000", "20,000"),
        ("20 000", "20.000"),
        ("20 000", "20000"),
        ("20.000", "20 000"),
        ("20.000", "20,000"),
    ],
)
def test_swedish_and_french_space_grouping(source_figure, answer_figure):
    source = f"Minsta beställning för en ny FBO är {source_figure} kr per månad."
    answer = f"Minsta beställning för en ny FBO är {answer_figure} kr per månad."

    repaired, removed = _repair(answer, source, title="Forever Sweden")

    assert removed == []
    assert repaired == answer


# ---------------------------------------------------------------------------
# Controls: decimals stay decimals, different figures stay different.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("figure", ["9,440", "9440", "9 440"])
def test_three_decimal_currency_is_not_read_as_a_thousands_group(figure):
    """Tunisian dinar has three decimal places: "9.440 TND" is nine dinars and 440 millimes."""
    source = "Minimum order size FBO: 9.440 TND."
    answer = f"The minimum order size for an FBO is {figure} TND."

    repaired, removed = _repair(answer, source, title="Forever Tunisia")

    assert removed == [figure]
    assert repaired == ""
    assert numbers_present_in_sources([figure], [_document(source, "Forever Tunisia")]) == {figure: False}


def test_case_credit_figure_with_a_three_digit_tail_stays_ambiguous():
    source = "The threshold is 1.000 Case Credits."
    answer = "The threshold is 1,000 Case Credits."

    _repaired, removed = _repair(answer, source, title="CA-EN-Company-Policy.pdf")

    assert removed == ["1,000"]


def test_figure_without_a_currency_stays_ambiguous():
    source = "• Delivery Cost: 2.000 until the highway (Maristes)."
    answer = "The delivery cost is 2,000 until the highway (Maristes)."

    _repaired, removed = _repair(answer, source)

    assert removed == ["2,000"]
    assert numbers_present_in_sources(["2,000"], [_document(source)]) == {"2,000": False}


@pytest.mark.parametrize(
    ("source", "answer", "figure"),
    [
        ("Minimum order size FBO: 1.5 CC per month.", "The minimum order size for an FBO is 15 CC per month.", "15"),
        ("Delivery Cost: 2.50 € per order.", "The delivery cost is 250 € per order.", "250"),
        ("Minimum order size FBO: 0,200CC as a first order.", "The minimum order size for an FBO is 200 CC as a first order.", "200"),
    ],
)
def test_decimal_figures_do_not_become_integers(source, answer, figure):
    _repaired, removed = _repair(answer, source)

    assert removed == [figure]


def test_zero_point_group_in_cc_is_not_two_hundred():
    source = "Minimum order size FBO: 0,200CC as a first order."

    assert numbers_present_in_sources(["200"], [_document(source)]) == {"200": False}


def test_a_different_figure_is_still_removed():
    source = "• Delivery Cost: 3.000 francs CFA from Maristes to Thiaroye."
    answer = "The delivery cost is 2,000 francs CFA from Maristes to Thiaroye."

    repaired, removed = _repair(answer, source)

    assert removed == ["2,000"]
    assert repaired == ""
    assert numbers_present_in_sources(["2,000"], [_document(source)]) == {"2,000": False}


@pytest.mark.parametrize("claim", ["2,000 Case Credits", "2000 CC", "2,000 TND", "2,000 days"])
def test_a_grouped_amount_supports_only_a_claim_that_could_be_the_same_money(claim):
    source = "• Delivery Cost: 2.000 francs CFA until the highway (Maristes)."
    answer = f"The delivery cost is {claim} until the highway (Maristes)."

    _repaired, removed = _repair(answer, source)

    assert removed == [claim.split(" ")[0]]


def test_a_grouped_figure_is_not_a_fragment_of_a_longer_number():
    """"12.000" must not lend "2000" to a claim, nor "2.000,50" lend "2000"."""
    for source in (
        "• Delivery Cost: 12.000 francs CFA until the highway.",
        "• Delivery Cost: 2.000,50 francs CFA until the highway.",
        "• Delivery Cost: 1.2.000 francs CFA until the highway.",
    ):
        assert numbers_present_in_sources(["2,000"], [_document(source)]) == {"2,000": False}, source
