"""Fable Phase 2 review corrections, findings 1 and 2: a bare newline was not
a unit boundary in utils.sentence_spans, so a label-style directory answer
("Telephone Office: ...\\nEmail: ...\\nWebsite: ...") or a heading/bullet
block ("## Bonus\\n...", "- claim\\n- ...") was read as ONE unit by both
`app/response/builder.py` (citation reconciliation) and
`app/evidence_contract.py` (grounding checks). Deterministic/local: pure
function and ResponseBuilder calls against local fixtures, no model or
network call. See docs/conversation-quality/phase2/FRAGMENT_AUDIT.md,
"Fable Phase 2 review corrections", for the full writeup.
"""

from __future__ import annotations

from app.evidence_contract import unsupported_answer_sentences
from app.response import ResponseBuilder
from app.retrieval import RetrievedDocument, RetrievalResult


# --- Finding 1: citation retention after a one-line removal ----------------


def _directory_document(content: str) -> RetrievedDocument:
    return RetrievedDocument(
        id="GLOBAL:sponsoring-ke",
        title="GLOBAL sponsoring-ke",
        content=content,
        source="s3://kb/dir-ke",
        country="GLOBAL",
        language="en",
        score=0.8,
        metadata={
            "directory_section": "sponsoring",
            "directory_kind": "international_sponsoring",
            "section_id": "sponsoring-ke",
        },
    )


_DIRECTORY_CONTENT = (
    "Telephone Office: +254 20 2026869\nEmail: info@foreverea.com\nWebsite: www.foreverea.com"
)


def test_citation_survives_a_one_line_removal_from_a_directory_answer() -> None:
    """Reproduction: before the fix, `split_sentences` (via a bare
    ``re.split(r"(?<=[.!?])\\s+|\\n", ...)`` in base, and via
    utils.sentence_spans before this fix) read the whole three-line block as
    ONE unit, because none of its lines end in "." "!" or "?". Removing just
    the Website line then made the WHOLE merged unit fail the "still present
    in delivered text" check, so `_surviving_text` returned "" and
    `reconcile_citations` dropped the citation entirely - even though the
    delivered answer still quotes the record's phone number and email.
    """
    documents = [_directory_document(_DIRECTORY_CONTENT)]
    result = RetrievalResult(documents, [], 0.9, metadata={"evidence_decision": {"approved": True}})
    builder = ResponseBuilder()
    built_answer = _DIRECTORY_CONTENT
    # A directory-field filter (remove_unrequested_directory_fields) drops the
    # one line the reader did not ask about.
    delivered_answer = "Telephone Office: +254 20 2026869\nEmail: info@foreverea.com"

    built = builder._supporting_citations(built_answer, result, session_country="KE")
    assert built, "the directory citation must be chosen before any edit"

    reconciled = builder.reconcile_citations(
        built_answer=built_answer,
        delivered_answer=delivered_answer,
        citations=built,
        retrieval_result=result,
        session_country="KE",
    )
    assert reconciled != [], "the citation must survive a one-line removal, not be dropped entirely"
    assert [citation.get("uri") for citation in reconciled] == ["s3://kb/dir-ke"]


def test_citation_survives_a_one_line_removal_after_a_numeric_repair_deletion() -> None:
    """The same shape, but the missing line is a numeric-repair deletion rather
    than a directory-field filter - the root cause (newline not a boundary)
    is identical either way."""
    documents = [_directory_document(_DIRECTORY_CONTENT)]
    result = RetrievalResult(documents, [], 0.9, metadata={"evidence_decision": {"approved": True}})
    builder = ResponseBuilder()
    built_answer = _DIRECTORY_CONTENT
    # Numeric repair removed the phone-number line as unsupported; the email
    # line survives untouched.
    delivered_answer = "Email: info@foreverea.com\nWebsite: www.foreverea.com"

    built = builder._supporting_citations(built_answer, result, session_country="KE")
    reconciled = builder.reconcile_citations(
        built_answer=built_answer,
        delivered_answer=delivered_answer,
        citations=built,
        retrieval_result=result,
        session_country="KE",
    )
    assert reconciled != []


def test_policy_citation_variant_survives_a_one_line_removal() -> None:
    """A policy citation (not a directory record) built from a multi-line,
    label-style answer with no terminal punctuation on either line also
    survives a one-line removal, through the same `_surviving_text` splitting
    - not only the directory-contact path above."""
    policy_document = RetrievedDocument(
        id="policy-1",
        title="Minimum order",
        content="Minimum order size FBO: 100 USD\nDelivery takes 3-5 working days",
        source="s3://kb/policy-1",
        country="KE",
        language="en",
        score=0.9,
    )
    result = RetrievalResult([policy_document], [], 0.9, metadata={"evidence_decision": {"approved": True}})
    builder = ResponseBuilder()
    built_answer = "Minimum order size FBO: 100 USD\nDelivery takes 3-5 working days"
    # A numeric-repair deletion removed the (invented) delivery-time line.
    delivered_answer = "Minimum order size FBO: 100 USD"

    built = builder._supporting_citations(built_answer, result, session_country="KE")
    assert built, "the policy citation must be chosen before any edit"

    reconciled = builder.reconcile_citations(
        built_answer=built_answer,
        delivered_answer=delivered_answer,
        citations=built,
        retrieval_result=result,
        session_country="KE",
    )
    assert reconciled != [], "the surviving line must still be enough to keep the policy citation"


def test_surviving_text_keeps_the_unaffected_lines_of_a_multiline_answer() -> None:
    """Direct unit check on `_surviving_text`: with the newline fix, only the
    REMOVED line is reported missing; the other lines are still "kept",
    unlike before, when the entire merged block was judged missing."""
    builder = ResponseBuilder()
    built_answer = _DIRECTORY_CONTENT
    delivered_answer = "Telephone Office: +254 20 2026869\nEmail: info@foreverea.com"
    surviving, complete = builder._surviving_text(built_answer, delivered_answer, [])
    assert not complete
    assert "Telephone Office: +254 20 2026869" in surviving
    assert "Email: info@foreverea.com" in surviving
    assert "Website: www.foreverea.com" not in surviving


# --- Finding 2: a heading/bullet line does not swallow the claim after it --


def test_heading_does_not_hide_the_unsupported_claim_sentence_after_it() -> None:
    """Reproduction: before the fix, "## Bonus\\nDistributors ... 500 USD ..."
    was ONE unit under `split_sentences`, and `_is_structural_line` skips a
    unit only when the WHOLE thing - heading included - is structural
    markdown. Because the merged unit also contained real prose, it was
    treated as non-structural and skipped nothing, OR (depending on content)
    read as starting with "#" and skipped as a whole, hiding the sentence
    from HistoryGroundingValidator's grounding check. After the fix, the
    heading is its own unit (skipped on its own) and the claim sentence is
    checked independently."""
    answer = (
        "## Bonus\nDistributors in Kenya receive a guaranteed monthly income "
        "bonus of 500 USD after sponsoring two people"
    )
    evidence = [
        "Distributors do not receive any guaranteed income bonus regardless of sponsorship activity."
    ]
    unsupported = unsupported_answer_sentences(answer, evidence)
    assert any("500 usd" in sentence.casefold() for sentence in unsupported)


def test_bullet_list_does_not_hide_the_unsupported_claim_in_the_next_bullet() -> None:
    """The same merge, for a bullet list instead of a heading: each "- ..."
    line must be checked as its own unit."""
    answer = (
        "- Distributors in Kenya receive a guaranteed monthly income bonus of 500 USD "
        "after sponsoring two people\n- Telephone Office: +254 20 2026869"
    )
    evidence = [
        "Distributors do not receive any guaranteed income bonus regardless of sponsorship activity."
    ]
    unsupported = unsupported_answer_sentences(answer, evidence)
    assert any("500 usd" in sentence.casefold() for sentence in unsupported)


def test_heading_line_alone_is_never_reported_as_an_unsupported_claim() -> None:
    """Negative control: the heading line itself (structural markdown, no
    factual assertion) must never appear in the unsupported list."""
    answer = "## Bonus\nDistributors in Kenya receive 500 USD after sponsoring two people"
    evidence = ["Distributors receive 500 USD after sponsoring two people."]
    unsupported = unsupported_answer_sentences(answer, evidence)
    assert not any(sentence.strip().startswith("#") for sentence in unsupported)
