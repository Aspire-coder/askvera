"""Which currency a bare figure is in, and when the source does not say.

Three layers decide it, and only the first two are evidence about the figure
itself:

    adjacent      the unit written beside the number
    governing     the unit stated earlier in the same row or clause
    declared      a heading or footer - a segment naming a unit and carrying
                  no figures - that covers this row

A claim whose unit none of those supplies is removed. The rule this replaced
asked only whether the claimed unit appeared somewhere before the figure, and
accepted anything at all when nothing did, so a document mentioning EUR once
licensed EUR on every bare number in it. Missing evidence is not support.

The counter-direction matters just as much: a false rejection deletes a
correct answer. Every case below is paired - the right claim must survive the
rule that removes the wrong one.
"""

from __future__ import annotations

import pytest

from app.retrieval.models import RetrievedDocument
from app.validation.validators import numeric_grounding_validator as validator
from app.validation.validators.numeric_grounding_validator import (
    unsupported_numeric_claims,
)


def _document(content: str) -> RetrievedDocument:
    return RetrievedDocument(
        id="section-1",
        title="DZ-FR-Company-Policy.pdf - Charges",
        content=content,
        source="s3://askverachat-prod-kb/approved/DZ_fr/policies/DZ-FR-Company-Policy.pdf",
        page="4",
        metadata={"access_scope": "country", "country": "DZ", "section_id": "section-1"},
    )


def _removed(answer: str, source: str) -> list[str]:
    return [
        claim.number
        for claim in unsupported_numeric_claims(answer, [_document(source)])
    ]


TWO_TABLES = (
    "Delivery charges - DZD\n"
    "Standard delivery: 900\n"
    "Membership charges - EUR\n"
    "Annual membership: 20\n"
)

BOTH_HEADINGS_FIRST = (
    "Delivery charges - DZD\n"
    "Membership charges - EUR\n"
    "Standard delivery: 900\n"
)

FOOTER = "Standard delivery: 900\nAll charges are stated in DZD.\n"

NEIGHBOURING_ROW = "Annual membership: 20 EUR\nStandard delivery: 900\n"


# --- multiple preceding currencies ----------------------------------------


def test_the_declaration_that_names_the_same_thing_as_the_row_governs_it() -> None:
    """Both headings precede the figure. Proximity picks the wrong one.

    "Membership charges - EUR" is nearer to the delivery row than the delivery
    heading is. Topic decides it instead, which is how a reader decides it.
    """
    assert _removed("Standard delivery costs 900 DZD.", BOTH_HEADINGS_FIRST) == []
    assert _removed("Standard delivery costs 900 EUR.", BOTH_HEADINGS_FIRST) == ["900"]


def test_a_later_table_does_not_lend_its_currency_backwards() -> None:
    assert _removed("Standard delivery costs 900 DZD.", TWO_TABLES) == []
    assert _removed("Standard delivery costs 900 EUR.", TWO_TABLES) == ["900"]


def test_the_second_table_keeps_its_own_currency() -> None:
    """The same rule read from the other end."""
    assert _removed("Annual membership costs 20 EUR.", TWO_TABLES) == []
    assert _removed("Annual membership costs 20 DZD.", TWO_TABLES) == ["20"]


def test_a_currency_beside_the_previous_row_does_not_govern_this_one() -> None:
    """A line break ends a table row.

    Without that, the unit written beside one row's figure became the nearest
    preceding unit for the next row's bare figure - the whole table inherited
    from whichever row happened to spell its currency out.
    """
    assert _removed("Standard delivery costs 900 EUR.", NEIGHBOURING_ROW) == ["900"]
    # And the row that does state its currency is unaffected.
    assert _removed("Annual membership costs 20 EUR.", NEIGHBOURING_ROW) == []


def test_a_declaration_naming_two_currencies_governs_neither() -> None:
    """"Prices in DZD or EUR" is not an answer to which one this row is in."""
    ambiguous = "Prices in DZD or EUR\nStandard delivery: 900\n"

    assert _removed("Standard delivery costs 900 DZD.", ambiguous) == ["900"]
    assert _removed("Standard delivery costs 900 EUR.", ambiguous) == ["900"]


# --- footer-scoped units ---------------------------------------------------


def test_a_footer_declaring_one_currency_governs_the_figures_above_it() -> None:
    """Documents commonly state the currency once, at the end."""
    assert _removed("Standard delivery costs 900 DZD.", FOOTER) == []


def test_a_footer_does_not_license_a_currency_it_does_not_name() -> None:
    mixed = "Standard delivery: 900\nAll charges are stated in DZD.\nMembership: 20 EUR\n"

    assert _removed("Standard delivery costs 900 EUR.", mixed) == ["900"]


def test_a_footer_governs_only_when_the_document_declares_one_unit() -> None:
    """Two footers and nothing before the figure is not inheritance, it is a guess."""
    two_footers = (
        "Standard delivery: 900\n"
        "Delivery charges are stated in DZD.\n"
        "Membership charges are stated in EUR.\n"
    )

    assert _removed("Standard delivery costs 900 DZD.", two_footers) == ["900"]


# --- no evidence at all ----------------------------------------------------


def test_a_unit_appearing_only_beside_another_figure_supports_nothing() -> None:
    """The strictness that replaced the permissive fallback.

    EUR is in the document, attached to a different row. That is not evidence
    about this one, and it used to be enough.
    """
    assert _removed("Standard delivery costs 900 EUR.", NEIGHBOURING_ROW) == ["900"]


def test_a_figure_with_no_unit_anywhere_supports_no_unit_claim() -> None:
    assert _removed("Standard delivery costs 900 DZD.", "Standard delivery: 900\n") == ["900"]


def test_a_claim_with_no_unit_is_unaffected_by_any_of_this() -> None:
    """Only a claim that names a unit can be wrong about the unit."""
    assert _removed("Standard delivery is 900.", "Standard delivery: 900\n") == []


def test_an_adjacent_unit_still_decides_it() -> None:
    """The first layer, unchanged, and the one that covers most real text."""
    assert _removed("Standard delivery costs 900 DZD.", "Standard delivery: 900 DZD\n") == []
    assert _removed("Standard delivery costs 900 EUR.", "Standard delivery: 900 DZD\n") == ["900"]


# --- the structure this depends on ----------------------------------------


def test_normalization_keeps_the_line_structure_the_rule_reads() -> None:
    """The rule is only as good as the structure that survives normalization.

    Collapsing every run of whitespace to a space - which is what normalization
    used to do - merges a heading into the row beneath it, and then nothing
    distinguishes a declaration from a data row.
    """
    normalized = validator._normalize("Delivery charges - DZD\nStandard delivery: 900")

    assert "\n" in normalized


def test_a_declaration_is_a_segment_with_a_unit_and_no_figure() -> None:
    declarations = validator._unit_declarations(
        validator._normalize(TWO_TABLES)
    )

    assert [declaration.unit for declaration in declarations] == ["dzd", "eur"]


@pytest.mark.parametrize(
    "line",
    [
        "standard delivery: 900 dzd",
        "the fee is 20 eur per year",
    ],
)
def test_a_row_carrying_a_figure_is_not_a_declaration(line: str) -> None:
    """A row's unit belongs to its own figure. Treating it as a heading would
    hand it to every bare number that follows."""
    assert validator._unit_declarations(validator._normalize(line)) == []


def test_the_subject_window_still_reads_across_line_breaks() -> None:
    """Two different boundaries, and confusing them breaks one or the other.

    A unit stops governing at a line break, because a line break ends a table
    row. The subject window deliberately does not stop there, because PDF
    extraction wraps one sentence over several lines and the subject that
    qualifies a figure is often on the line above it.
    """
    wrapped = "The GO2FBO pack for new distributors\ncosts 352.38 EUR in total\n"

    assert _removed("The GO2FBO pack costs 352.38 EUR.", wrapped) == []
