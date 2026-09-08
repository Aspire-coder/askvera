"""Figures split from the heading that gives them meaning.

A table states its currency once, in a heading, and leaves the rows bare.
Grounding lets that heading govern a figure up to 300 characters later. But
retrieval returns chunks, not documents, so where the document was cut changes
what the validator can see.

Two defects were found here and both are now fixed: a currency heading too far
above its rows was lost to chunking, deleting correct figures, and an
ungoverned figure accepted any unit the document mentioned anywhere, letting
wrong ones through. The tests that recorded them assert the corrected
behaviour, and each keeps the counter-case that stops the fix going too far.
"""

from __future__ import annotations

from app.retrieval.models import RetrievedDocument
from app.validation.validators import numeric_grounding_validator as validator
from app.validation.validators.numeric_grounding_validator import (
    unsupported_numeric_claims,
)
from services.knowledge_ingestion import (
    CHUNK_OVERLAP_CHARS,
    MAX_CHUNK_CHARS,
    ExtractedPage,
    _carry_unit_context,
    _chunk_text,
    build_sections,
)


def _document(content: str) -> RetrievedDocument:
    return RetrievedDocument(
        id="section-1",
        title="DZ-FR-Company-Policy.pdf - Delivery charges",
        content=content,
        source="s3://askverachat-prod-kb/approved/DZ_fr/policies/DZ-FR-Company-Policy.pdf",
        page="12",
        metadata={"access_scope": "country", "country": "DZ", "section_id": "section-1"},
    )


def _numbers(answer: str, documents: list[RetrievedDocument]) -> list[str]:
    return [claim.number for claim in unsupported_numeric_claims(answer, documents)]


def test_the_overlap_is_wider_than_the_unit_lookback() -> None:
    """The invariant that makes a nearby heading survive the cut.

    A heading within the 300-character lookback is what binds a bare row to its
    currency. The chunker overlaps by 450 characters, so such a heading is
    still in the same chunk as the row it governs. If someone tunes the overlap
    down or the lookback up, that stops being true and correct answers quietly
    lose figures - a silent failure, which is why it is asserted here.
    """
    assert CHUNK_OVERLAP_CHARS > validator._UNIT_LOOKBACK_CHARACTERS


def test_the_chunker_keeps_the_overlap_it_promises() -> None:
    """_chunk_text moves each boundary to a line break, shortening the overlap.

    The constant is the intent; this is the delivered overlap.
    """
    text_value = "".join(f"Line {index} of the charges table.\n" for index in range(400))
    chunks = _chunk_text(text_value, max_chars=MAX_CHUNK_CHARS, overlap_chars=CHUNK_OVERLAP_CHARS)

    assert len(chunks) > 1
    for earlier, later in zip(chunks, chunks[1:]):
        overlap_length = 0
        for length in range(min(len(earlier), len(later)), 0, -1):
            if earlier.endswith(later[:length]):
                overlap_length = length
                break
        assert overlap_length > validator._UNIT_LOOKBACK_CHARACTERS, (
            f"overlap of {overlap_length} characters is shorter than the "
            f"{validator._UNIT_LOOKBACK_CHARACTERS}-character unit lookback"
        )


def test_a_nearby_heading_survives_a_chunk_boundary_between_it_and_the_row() -> None:
    """The case the overlap covers, exercised rather than reasoned about."""
    heading = "Delivery charges for this market are stated in DZD\n"
    padding = "".join(f"Zone {index} handling note\n" for index in range(1, 9))
    row = "Standard delivery to the Algiers office: 900\n"
    # Small chunks, so a boundary is forced between the heading and the row.
    chunks = _chunk_text(
        "".join(f"Preamble line {index}\n" for index in range(60)) + heading + padding + row,
        max_chars=400,
        overlap_chars=180,
    )
    assert len(chunks) > 1
    documents = [_document(chunk) for chunk in chunks]

    assert _numbers("Standard delivery to the Algiers office costs 900 DZD.", documents) == []


def test_a_distant_heading_is_carried_onto_the_chunks_that_continue_the_table() -> None:
    """Fixed. This used to delete a correct figure.

    The currency is stated once at the top of a long table and the row is
    thousands of characters below it, far outside both the lookback and the
    chunk overlap. The row's chunk contained no currency at all, so a correct
    claim was rejected - a true statement deleted, which is worse than a
    doubtful one getting through.

    Ingestion now carries the declaring line onto continuation chunks, so the
    evidence travels with the rows it explains.
    """
    heading = "Delivery and membership charges are stated in DZD.\n"
    filler = "".join(f"Zone {index} standard handling: {100 + index}\n" for index in range(1, 260))
    row = "Standard delivery to the Algiers office: 900\n"
    document_text = heading + filler + row

    raw = _chunk_text(document_text, max_chars=1200, overlap_chars=450)
    assert len(raw) > 1
    assert "DZD" not in raw[-1], "the fixture must reproduce the original split"

    carried = _carry_unit_context(raw)
    answer = "Standard delivery to the Algiers office costs 900 DZD."

    assert _numbers(answer, [_document(chunk) for chunk in raw]) == ["900"], (
        "unchanged chunks still lose the figure"
    )
    assert _numbers(answer, [_document(chunk) for chunk in carried]) == [], (
        "carrying the heading restores it"
    )


def test_the_carried_heading_does_not_override_a_chunk_that_states_its_own() -> None:
    """A continuation that declares a different currency keeps it.

    Otherwise the fix for one defect creates the other: a membership table
    priced in EUR, following a delivery table priced in DZD, would be labelled
    DZD by the thing meant to help it.
    """
    chunks = _carry_unit_context(
        [
            "Delivery charges are stated in DZD\nStandard delivery: 900\n",
            "Membership charges are stated in EUR\nAnnual membership: 20\n",
            "Replacement card: 5\n",
        ]
    )

    assert chunks[1].startswith("Membership charges")
    assert "DZD" not in chunks[1]
    # And the third, which states nothing, inherits the nearer heading.
    assert "EUR" in chunks[2]
    assert "DZD" not in chunks[2]

    documents = [_document(chunk) for chunk in chunks]
    assert _numbers("Annual membership costs 20 EUR.", documents) == []
    assert _numbers("Annual membership costs 20 DZD.", documents) == ["20"]


def test_a_single_chunk_document_is_left_exactly_as_it_was() -> None:
    """Most documents are one chunk. They must not be touched at all."""
    assert _carry_unit_context(["Charges in DZD\nStandard delivery: 900\n"]) == [
        "Charges in DZD\nStandard delivery: 900\n"
    ]


def test_a_long_paragraph_mentioning_a_currency_is_not_carried_as_a_heading() -> None:
    """A heading is short. A paragraph that happens to name a currency is not one,
    and copying it onto every following chunk would be noise in the retrieved text."""
    paragraph = (
        "Distributors should note that all charges described in this policy, "
        "including delivery, membership and replacement charges, are stated in "
        "DZD unless the relevant section says otherwise, and that local taxes "
        "may apply in addition to the amounts shown in the tables below.\n"
    )
    chunks = _carry_unit_context([paragraph, "Standard delivery: 900\n"])

    assert chunks[1] == "Standard delivery: 900\n"


def test_the_emitted_chunks_of_a_real_ingestion_carry_the_heading() -> None:
    """The actual ingestion path, not _chunk_text called directly.

    Asserting that the overlap constant exceeds the lookback constant is an
    argument about two numbers. This runs a document through the function that
    builds sections and looks at what it emitted.
    """
    heading = "All charges in this directory are stated in DZD.\n"
    filler = "".join(f"Zone {index} standard handling: {100 + index}\n" for index in range(1, 400))
    row = "Standard delivery to the Algiers office: 900\n"

    sections = build_sections(
        [ExtractedPage(number=1, text=heading + filler + row)],
        filename="DZ-FR-Charges.pdf",
        country="DZ",
        language="fr",
        document_type="policy",
    )

    assert len(sections) > 1, "the fixture must actually be split"
    row_sections = [s for s in sections if "Algiers office: 900" in s["content"]]
    assert row_sections, "the row must appear in some emitted section"
    for section in row_sections:
        assert "DZD" in section["content"], (
            "the emitted chunk holding the row does not state its currency"
        )

    documents = [_document(section["content"]) for section in sections]
    assert _numbers("Standard delivery to the Algiers office costs 900 DZD.", documents) == []


def test_a_wrong_currency_is_rejected_when_the_source_never_names_it() -> None:
    """The check that stops the tests above from passing for the wrong reason."""
    documents = [_document("Delivery charges are stated in DZD.\nStandard delivery: 900\n")]

    assert _numbers("Standard delivery costs 900 EUR.", documents) == ["900"]


def test_a_table_continuation_header_governs_the_rows_that_follow_it() -> None:
    """PDF tables repeat their header when they run onto the next page.

    Extraction keeps both, so the continuation header is what the later rows
    inherit from.
    """
    documents = [
        _document(
            "Membership charges (continued) - all amounts in EUR\n"
            "Annual membership: 20\n"
            "Replacement card: 5\n"
        )
    ]

    assert _numbers("Annual membership costs 20 EUR.", documents) == []
    assert _numbers("Annual membership costs 20 DZD.", documents) == ["20"]


def test_a_row_does_not_take_a_currency_from_a_different_table() -> None:
    """Fixed. This used to accept the wrong currency.

    Two tables, both currencies present. Inheritance is bounded by the clause
    delimiter and that bound is right - it stops DZD governing across a full
    stop, which is what keeps a correct claim from being rejected. But when
    nothing governed an occurrence the check fell back to document-wide
    presence and accepted any unit named anywhere. EUR is named, by the
    membership table, so a delivery charge in DZD passed as EUR.

    Now an ungoverned figure is checked against the units stated BEFORE it: a
    unit that never precedes the figure cannot be what it is denominated in.
    """
    with_stops = (
        "Delivery charges - DZD.\n"
        "Standard delivery: 900.\n"
        "Membership charges - EUR.\n"
        "Annual membership: 20.\n"
    )
    without_stops = with_stops.replace(".\n", "\n")

    for source in (with_stops, without_stops):
        documents = [_document(source)]
        assert _numbers("Standard delivery costs 900 EUR.", documents) == ["900"]
        # And the correct claim still passes, in both layouts. Rejecting the
        # wrong currency is worth nothing if it costs the right one.
        assert _numbers("Standard delivery costs 900 DZD.", documents) == []


def test_a_currency_two_sentences_back_still_supports_a_correct_claim() -> None:
    """The false rejection that made inheritance clause-bounded in the first place.

    Nothing governs 900 here either - the intervening sentence ends before it.
    What saves the claim is that DZD does precede the figure, so it is not
    contradicted. A rule that simply took the nearest preceding unit would pick
    EUR and delete a correct figure.
    """
    documents = [
        _document(
            "Delivery charges - DZD. Membership fees are payable in EUR each year. "
            "Standard delivery: 900\n"
        )
    ]

    assert _numbers("Standard delivery costs 900 DZD.", documents) == []


def test_a_unit_stated_only_after_the_figure_is_not_treated_as_contradicted() -> None:
    """A footer declaring the currency is common, and proves nothing against it.

    With no unit before the figure there is no evidence about which currency it
    is in, and absence of evidence must not become a rejection.
    """
    documents = [_document("Standard delivery: 900\nAll charges are stated in DZD.\n")]

    assert _numbers("Standard delivery costs 900 DZD.", documents) == []
