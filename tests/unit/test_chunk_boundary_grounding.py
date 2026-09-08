"""Figures split from the heading that gives them meaning.

A table states its currency once, in a heading, and leaves the rows bare.
Grounding lets that heading govern a figure up to 300 characters later. But
retrieval returns chunks, not documents, so where the document was cut changes
what the validator can see.

Two of these tests record behaviour that is wrong, and are written to pass
against it. Both are marked. A test that asserts the behaviour we want and
fails is a broken build; a test that asserts what happens, and says plainly
that it is wrong, is a record that survives until someone fixes it.
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
    _chunk_text,
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


def test_a_distant_heading_does_not_survive_chunking() -> None:
    """WRONG BEHAVIOUR, recorded. A correct figure is removed.

    The currency is stated once at the top of a long table and the row is
    thousands of characters below it. In the whole document the currency is
    present, so the claim is grounded. Chunked, the row's chunk does not
    contain the word DZD at all, _unit_appears_in fails, and a correct answer
    loses the figure.

    Nothing here is a fabrication getting through - it is the opposite, a true
    statement being deleted, which is the failure mode that damages a correct
    answer rather than letting a wrong one out. It is not fixed by widening the
    lookback: the fix is either to carry the governing heading onto the chunk
    at ingestion, or to let a unit named in a sibling chunk of the same
    document count. Both are changes to make deliberately, not while writing a
    test that discovered the problem.
    """
    heading = "Delivery and membership charges are stated in DZD.\n"
    filler = "".join(f"Zone {index} standard handling: {100 + index}\n" for index in range(1, 260))
    row = "Standard delivery to the Algiers office: 900\n"
    document_text = heading + filler + row

    whole = [_document(document_text)]
    chunks = _chunk_text(document_text, max_chars=1200, overlap_chars=450)
    assert len(chunks) > 1
    assert "DZD" not in chunks[-1]

    answer = "Standard delivery to the Algiers office costs 900 DZD."

    assert _numbers(answer, whole) == [], "grounded in the whole document"
    assert _numbers(answer, [_document(chunk) for chunk in chunks]) == ["900"], (
        "and removed once the same document is chunked"
    )


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


def test_a_row_inherits_the_wrong_currency_when_a_full_stop_intervenes() -> None:
    """WRONG BEHAVIOUR, recorded. A wrong currency is accepted.

    Two tables, both currencies present. Inheritance is bounded by the clause
    delimiter, and that bound is doing its job: the full stop after DZD stops
    it governing the row below. But when nothing governs an occurrence,
    _source_windows accepts whatever unit the answer states, so far as the
    document mentions it somewhere - and EUR is mentioned, by the other table.

    So "Standard delivery costs 900 EUR" passes, and it is wrong. This is the
    permissive half of unit binding, and it is the one that lets a wrong answer
    out rather than deleting a right one.

    The same layout without the full stops is rejected correctly, which is what
    the second half of this test shows: the gap is specifically that a clause
    boundary turns a governed figure into an ungoverned one.
    """
    with_stops = [
        _document(
            "Delivery charges - DZD.\n"
            "Standard delivery: 900.\n"
            "Membership charges - EUR.\n"
            "Annual membership: 20.\n"
        )
    ]
    without_stops = [
        _document(
            "Delivery charges - DZD\n"
            "Standard delivery: 900\n"
            "Membership charges - EUR\n"
            "Annual membership: 20\n"
        )
    ]

    assert _numbers("Standard delivery costs 900 EUR.", with_stops) == [], "wrong, recorded"
    assert _numbers("Standard delivery costs 900 EUR.", without_stops) == ["900"]
