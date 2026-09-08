"""The publication gate must not be talkable-around.

Every test here is about a way publication could be obtained without the
document actually being fit to publish: waiving a contradiction, reusing an old
approval, approving without saying who or why, or turning a flag on.
"""

from __future__ import annotations

import pytest

from services.metadata_conflicts import MetadataFinding, Severity
from services.publication_gate import (
    PublicationBlocked,
    evaluate_publication,
    record_resolution,
    revision_fingerprint,
)

REVISION = "revision-one"


def _contradiction() -> MetadataFinding:
    return MetadataFinding("expiry_date", Severity.CONTRADICTION, "Expiry precedes effective.")


def _unresolved() -> MetadataFinding:
    return MetadataFinding("effective_date", Severity.UNRESOLVED, "No effective date supplied.")


def _approval(revision: str = REVISION):
    return record_resolution(
        revision=revision, decided_by="reviewer@example.com", decision="publish",
        reason="Confirmed against the source document.",
    )


def _evaluate(**overrides):
    arguments = {
        "findings": [],
        "extraction_blocking_pages": [],
        "extraction_uncertain_pages": [],
        "revision": REVISION,
        "resolution": None,
    }
    arguments.update(overrides)
    return evaluate_publication(**arguments)


def test_a_clean_document_publishes() -> None:
    """The control. Without it, a gate that blocked everything would pass."""
    _evaluate()


def test_a_contradiction_cannot_be_waived_by_any_approval() -> None:
    """The property the gate exists for.

    An expiry preceding its own effective date is not a judgement call. A
    reviewer who approves it has approved something that cannot be true, so the
    approval is ignored rather than honoured.
    """
    with pytest.raises(PublicationBlocked) as blocked:
        _evaluate(findings=[_contradiction()], resolution=_approval())

    assert any("cannot be waived" in reason for reason in blocked.value.reasons)


def test_confirmed_missing_content_blocks_regardless_of_approval() -> None:
    """Unreadable content is recovered or replaced, not signed off."""
    with pytest.raises(PublicationBlocked) as blocked:
        _evaluate(extraction_blocking_pages=[4, 5], resolution=_approval())

    assert any("could not be extracted" in reason for reason in blocked.value.reasons)
    assert any("4, 5" in reason for reason in blocked.value.reasons)


def test_an_uncertain_page_needs_a_decision_and_then_publishes() -> None:
    """Suspicious is not the same as broken.

    A readable heading above something unreadable may be a letterhead or may be
    a scanned fee table. A person decides; the gate refuses to guess in either
    direction.
    """
    with pytest.raises(PublicationBlocked):
        _evaluate(extraction_uncertain_pages=[7])

    _evaluate(extraction_uncertain_pages=[7], resolution=_approval())


def test_an_unresolved_finding_needs_a_decision_and_then_publishes() -> None:
    with pytest.raises(PublicationBlocked):
        _evaluate(findings=[_unresolved()])

    _evaluate(findings=[_unresolved()], resolution=_approval())


def test_an_approval_of_a_different_revision_does_not_carry_over() -> None:
    """The stale-approval hole.

    A decision records what someone concluded about a specific document. Once
    the document or its metadata changes, that conclusion describes something
    that no longer exists, and honouring it would publish one thing on the
    authority of an approval of another.
    """
    with pytest.raises(PublicationBlocked) as blocked:
        _evaluate(findings=[_unresolved()], resolution=_approval("an-older-revision"))

    assert any("different revision" in reason for reason in blocked.value.reasons)


def test_a_rejection_is_not_an_approval() -> None:
    rejection = record_resolution(
        revision=REVISION, decided_by="reviewer@example.com", decision="reject",
        reason="Wrong market on the cover page.",
    )
    with pytest.raises(PublicationBlocked):
        _evaluate(findings=[_unresolved()], resolution=rejection)


def test_every_reason_is_reported_not_only_the_first() -> None:
    """A reviewer should see the whole picture rather than one problem per attempt."""
    with pytest.raises(PublicationBlocked) as blocked:
        _evaluate(
            findings=[_contradiction(), _unresolved()],
            extraction_blocking_pages=[2],
            extraction_uncertain_pages=[9],
        )

    assert len(blocked.value.reasons) == 3


@pytest.mark.parametrize("missing", ["decided_by", "reason", "revision"])
def test_a_resolution_missing_who_why_or_what_is_refused(missing: str) -> None:
    """An unexplained approval is indistinguishable from an accidental one when
    it is read back a year later."""
    arguments = {
        "revision": REVISION, "decided_by": "reviewer@example.com",
        "decision": "publish", "reason": "Checked.",
    }
    arguments[missing] = "   "
    with pytest.raises(ValueError):
        record_resolution(**arguments)


def test_a_resolution_records_who_what_why_and_when() -> None:
    resolution = _approval()
    assert resolution.decided_by == "reviewer@example.com"
    assert resolution.decision == "publish"
    assert resolution.reason
    assert resolution.decided_at.endswith("+00:00")


def test_changing_metadata_changes_the_revision() -> None:
    """Metadata is part of the revision, not a label on it.

    Re-declaring a document's country changes what publishing it means even
    when the bytes are identical, so an approval taken before that change must
    not carry over.
    """
    base = {"country": "DK", "language": "en", "document_type": "policy",
            "version": "2026-07", "effective_date": "2026-07-01"}

    unchanged = revision_fingerprint(content_hash="abc", metadata=dict(base))
    assert revision_fingerprint(content_hash="abc", metadata=dict(base)) == unchanged

    assert revision_fingerprint(content_hash="abc", metadata={**base, "country": "SE"}) != unchanged
    assert revision_fingerprint(content_hash="different", metadata=dict(base)) != unchanged


def test_no_flag_appears_in_this_module() -> None:
    """Staging is not evidence that review happened.

    ADMIN_INGESTION_STAGED_PUBLISH_ENABLED controls whether documents are staged
    before activation. It says nothing about whether a person looked at the
    findings, so the gate does not read it, and no setting can switch the gate
    off.
    """
    import inspect

    from services import publication_gate

    source = inspect.getsource(publication_gate)
    assert "settings" not in source
    assert "STAGED_PUBLISH" not in source
    assert "import config" not in source


def test_the_gate_is_enforced_inside_publish_not_in_the_route() -> None:
    """A direct API call or a retry must hit the same check.

    Enforcement in the route would be bypassed by any other caller. The service
    function is where every publication path arrives, so the check lives there.
    """
    import inspect

    from services import knowledge_ingestion

    source = inspect.getsource(knowledge_ingestion.publish_ingestion_job)
    assert "_enforce_publication_gate" in source
    # Before the staging verification and the index activation, so a blocked
    # document never reaches either.
    assert source.index("_enforce_publication_gate") < source.index("_staging_documents")


def test_publication_is_refused_when_metadata_contradicts_itself() -> None:
    """End to end through the service function, with the job store stubbed."""
    from services import knowledge_ingestion

    job = {
        "job_id": "job-1", "status": "ready_for_review", "filename": "DK-EN-Company-Policy.pdf",
        "country": "DK", "language": "EN", "document_type": "policy", "version": "2026-07",
        "effective_date": "2026-07-01", "expiry_date": "2026-01-01", "content_hash": "abc",
    }

    with pytest.raises(ValueError) as refused:
        knowledge_ingestion._enforce_publication_gate(job, None)

    assert "cannot be waived" in str(refused.value)


def test_an_uncertain_page_blocks_until_a_reviewer_decides_on_that_revision() -> None:
    from services import knowledge_ingestion
    from services.publication_gate import record_resolution, revision_fingerprint

    job = {
        "job_id": "job-2", "status": "ready_for_review", "filename": "DK-EN-Company-Policy.pdf",
        "country": "DK", "language": "EN", "document_type": "policy", "version": "2026-07",
        "effective_date": "2026-07-01", "expiry_date": "", "content_hash": "abc",
        "low_text_image_pages": [7],
    }

    with pytest.raises(ValueError) as refused:
        knowledge_ingestion._enforce_publication_gate(job, None)
    assert "completeness is uncertain" in str(refused.value)

    metadata = {key: job[key] for key in (
        "filename", "country", "language", "document_type", "version",
        "effective_date", "expiry_date")}
    metadata["access_scope"] = ""
    approval = record_resolution(
        revision=revision_fingerprint(content_hash="abc", metadata=metadata),
        decided_by="reviewer@example.com", decision="publish",
        reason="Page 7 is the letterhead; confirmed against the printed copy.",
    )
    knowledge_ingestion._enforce_publication_gate(job, approval)

    # Re-declaring the market invalidates that decision.
    with pytest.raises(ValueError) as stale:
        knowledge_ingestion._enforce_publication_gate({**job, "country": "SE"}, approval)
    assert "different revision" in str(stale.value)


# ---------------------------------------------------------------------------
# Every activation path, not only the reviewed one.
#
# Putting a check in publish_ingestion_job covers its callers and proves
# nothing about other code that activates a generation. There is a second path:
# when review_before_publish is false, processing activates the sections and the
# generation pointer directly, and publish_ingestion_job is never involved.
# ---------------------------------------------------------------------------


def test_there_are_exactly_two_activation_paths_and_both_are_gated() -> None:
    """A new activation call site must not appear unnoticed.

    _activate_staged_sections and _activate_generation_pointer are the two
    functions that make staged content live. If a third caller is added, this
    fails and whoever added it has to say how it reaches the gate.
    """
    import inspect

    from services import knowledge_ingestion

    source = inspect.getsource(knowledge_ingestion)
    assert source.count("_activate_staged_sections(") == 3  # definition plus two calls
    assert source.count("_activate_generation_pointer(") == 3

    # The processing-path calls are gated on review_before_publish, and that
    # flag is forced true when findings exist.
    process = inspect.getsource(knowledge_ingestion.process_ingestion_job)
    assert "_findings_require_review(" in process
    assert process.index("_findings_require_review(") < process.index("_index_sections(")


def test_a_contradiction_withholds_automatic_publication() -> None:
    """The hole this closes.

    review_before_publish arrives as a form field defaulting to true, and a
    caller holding publish permission can submit false. Both activation calls
    are gated on it, so before this a document whose expiry preceded its own
    effective date went straight into the index with no check at all.
    """
    from services import knowledge_ingestion

    assert knowledge_ingestion._findings_require_review(
        job_id="job-1", filename="DK-EN-Company-Policy.pdf", country="DK", language="EN",
        document_type="policy", version="2026-07",
        effective_date="2026-07-01", expiry_date="2026-01-01", low_text_image_pages=[],
    ) is True


def test_an_uncertain_page_withholds_automatic_publication() -> None:
    from services import knowledge_ingestion

    assert knowledge_ingestion._findings_require_review(
        job_id="job-2", filename="DK-EN-Company-Policy.pdf", country="DK", language="EN",
        document_type="policy", version="2026-07",
        effective_date="2026-07-01", expiry_date="", low_text_image_pages=[7],
    ) is True


def test_a_clean_document_still_publishes_automatically() -> None:
    """Routing everything to review would be a different kind of broken.

    The point is that a document with nothing wrong keeps the behaviour it had.
    """
    from services import knowledge_ingestion

    assert knowledge_ingestion._findings_require_review(
        job_id="job-3", filename="DK-EN-Company-Policy.pdf", country="DK", language="EN",
        document_type="policy", version="2026-07",
        effective_date="2026-07-01", expiry_date="", low_text_image_pages=[],
    ) is False


def test_review_before_publish_is_only_ever_forced_on_never_off() -> None:
    """A client-supplied flag may add review and must not remove it."""
    import inspect

    from services import knowledge_ingestion

    process = inspect.getsource(knowledge_ingestion.process_ingestion_job)
    assert "review_before_publish = review_before_publish or _findings_require_review(" in process
