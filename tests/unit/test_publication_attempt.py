"""Publication interrupted at each point it can be interrupted.

The store is faked so a failure can be injected exactly where it matters. What
that establishes is the state machine's behaviour, not PostgreSQL's: whether a
conditional UPDATE really serialises two workers is a database property, and
proving it needs the database. That claim is pending with the rest of the
PostgreSQL validation.
"""

from __future__ import annotations

import pytest

from services import publication_attempt as attempt
from services.publication_attempt import (
    FAILED_RECOVERABLE,
    IN_PROGRESS,
    NOT_STARTED,
    SUCCEEDED,
    AttemptRecord,
    PublicationConflict,
)

JOB = "job-1"
REVISION = "rev-a"
DOCUMENT = "country:DK:en:policy:company-policy"


class FakeStore:
    """An in-memory store whose claim() is genuinely conditional."""

    def __init__(self, *, state=NOT_STARTED, revision=REVISION, key="", pointer=""):
        self.record = AttemptRecord(
            job_id=JOB, revision=revision, state=state, attempt_key=key
        )
        self.pointer = pointer
        self.settled: list[tuple[str, str]] = []
        self.claims = 0

    def read(self, job_id):
        return self.record

    def claim(self, *, job_id, revision, key):
        self.claims += 1
        if self.record.revision and self.record.revision != revision:
            return False
        if self.record.state not in (NOT_STARTED, FAILED_RECOVERABLE):
            return False
        self.record = AttemptRecord(
            job_id=job_id, revision=revision, state=IN_PROGRESS, attempt_key=key
        )
        return True

    def settle(self, *, job_id, state, detail):
        self.settled.append((state, detail))
        self.record = AttemptRecord(
            job_id=job_id,
            revision=self.record.revision,
            state=state,
            attempt_key=self.record.attempt_key,
            detail=detail,
        )

    def active_ingestion_id(self, logical_document_id):
        return self.pointer


def _begin(store):
    return attempt.begin(
        store, job_id=JOB, revision=REVISION, logical_document_id=DOCUMENT
    )


def test_a_first_attempt_claims_the_job() -> None:
    store = FakeStore()
    claimed = _begin(store)

    assert claimed is not None
    assert claimed.state == IN_PROGRESS
    assert claimed.attempt_key == f"{JOB}:{REVISION}"


def test_failure_before_activation_leaves_a_retryable_state() -> None:
    """Nothing was activated, so nothing is visible and a retry is safe."""
    store = FakeStore()
    _begin(store)
    attempt.fail(store, job_id=JOB, detail="OpenSearch unreachable")

    assert store.record.state == FAILED_RECOVERABLE
    # And the retry is allowed to proceed.
    assert _begin(store) is not None


def test_failure_between_activation_and_the_pointer_is_recovered_as_unpublished() -> None:
    """The window the design exists for.

    Sections are active in the index but the pointer never moved. Retrieval
    filters on the pointer, so a reader sees nothing - which is why redoing the
    work is safe rather than a double publication.
    """
    store = FakeStore(state=IN_PROGRESS, key=f"{JOB}:{REVISION}", pointer="")

    resumed = _begin(store)

    assert resumed is not None
    assert resumed.state == IN_PROGRESS
    assert store.settled == []


def test_failure_after_the_pointer_moved_is_recovered_as_published() -> None:
    """An exception is not evidence that activation failed.

    The worker died after the commit point. Assuming failure here would
    republish a document that is already live; the pointer is asked instead.
    """
    store = FakeStore(state=IN_PROGRESS, key=f"{JOB}:{REVISION}", pointer=JOB)

    assert _begin(store) is None
    assert store.settled == [(SUCCEEDED, "recovered: pointer already active")]


def test_a_duplicate_request_does_not_activate_a_second_time() -> None:
    store = FakeStore(state=SUCCEEDED, key=f"{JOB}:{REVISION}", pointer=JOB)

    assert _begin(store) is None
    assert store.claims == 0


def test_a_concurrent_attempt_is_refused_rather_than_queued() -> None:
    """Two workers, and the second must not proceed on the same revision."""
    store = FakeStore()
    assert _begin(store) is not None

    # The second worker sees in_progress and asks the pointer; nothing is live,
    # so it resumes. That is correct for a dead worker and wrong for a live one,
    # which is why the conditional claim - not this path - is what serialises
    # two workers that are both actually running. Verified against PostgreSQL
    # is pending; here only the claim's conditionality is checked.
    store.record = AttemptRecord(
        job_id=JOB, revision=REVISION, state=IN_PROGRESS, attempt_key="other:key"
    )
    with pytest.raises(PublicationConflict):
        _begin(store)


def test_a_metadata_edit_invalidates_an_attempt_authorised_for_other_content() -> None:
    """The edit wins, because publishing would ship content nobody approved."""
    store = FakeStore(revision="rev-b")

    with pytest.raises(PublicationConflict) as raised:
        _begin(store)

    assert "changed since this approval" in str(raised.value)
    assert store.claims == 0


def test_the_idempotency_key_is_bound_to_the_revision() -> None:
    first = attempt.attempt_key(job_id=JOB, revision="rev-a")
    second = attempt.attempt_key(job_id=JOB, revision="rev-b")

    assert first != second


def test_confirmation_reads_the_pointer_rather_than_trusting_the_call() -> None:
    store = FakeStore(state=IN_PROGRESS, key=f"{JOB}:{REVISION}", pointer=JOB)

    attempt.confirm(
        store, job_id=JOB, logical_document_id=DOCUMENT, pointer_enabled=True
    )

    assert store.settled == [(SUCCEEDED, "pointer confirmed")]


def test_activation_that_did_not_take_effect_is_reported_not_recorded_as_success() -> None:
    """No exception was raised and the document is still not live."""
    store = FakeStore(state=IN_PROGRESS, key=f"{JOB}:{REVISION}", pointer="someone-else")

    with pytest.raises(RuntimeError):
        attempt.confirm(
            store, job_id=JOB, logical_document_id=DOCUMENT, pointer_enabled=True
        )

    assert store.record.state == FAILED_RECOVERABLE


def test_without_the_pointer_success_is_recorded_as_unverified() -> None:
    """There is no authority to consult, and the record says so.

    With ADMIN_INGESTION_GENERATION_POINTER_ENABLED off, retrieval has no
    generation filter and publication has no commit point. Recording a
    confirmation that was never made would be the wrong kind of tidy.
    """
    store = FakeStore(state=IN_PROGRESS, key=f"{JOB}:{REVISION}")

    attempt.confirm(
        store, job_id=JOB, logical_document_id=DOCUMENT, pointer_enabled=False
    )

    state, detail = store.settled[0]
    assert state == SUCCEEDED
    assert "unverified" in detail


def test_a_lost_failure_record_does_not_mask_the_original_error() -> None:
    """The job stays in_progress, which is exactly what recovery interprets."""

    class Broken(FakeStore):
        def settle(self, **kwargs):
            raise RuntimeError("database gone")

    store = Broken(state=IN_PROGRESS, key=f"{JOB}:{REVISION}")
    attempt.fail(store, job_id=JOB, detail="original cause")

    assert store.record.state == IN_PROGRESS


def test_recovery_never_reads_the_cached_generation_lookup() -> None:
    """active_generation_ids caches for 15 seconds; recovery asks what is true now."""
    import inspect
    import re

    source = inspect.getsource(attempt.PostgresAttemptStore.active_ingestion_id)
    # Comments first. The comment here explains why the cached lookup is not
    # used, and matching the raw text found the explanation rather than a call
    # - the same mistake stripped comments out of the migration checks.
    code = "\n".join(re.sub(r"#.*$", "", line) for line in source.splitlines())
    assert "active_generation_ids" not in code
    assert "knowledge_active_generations" in source


def test_a_visibility_lookup_failure_is_not_read_as_unpublished() -> None:
    """Returning "" on error would invite a retry on a live document."""

    class Failing(FakeStore):
        def active_ingestion_id(self, logical_document_id):
            raise RuntimeError("database unreachable")

    store = Failing(state=IN_PROGRESS, key=f"{JOB}:{REVISION}")
    with pytest.raises(RuntimeError):
        _begin(store)


def test_the_claim_statement_is_conditional_in_one_write() -> None:
    """Read-then-write would let two workers both see not_started."""
    import inspect

    source = inspect.getsource(attempt.PostgresAttemptStore.claim)
    assert "UPDATE ingestion_jobs" in source
    assert "AND review_revision = :revision" in source
    assert "publication_state IN ('not_started', 'failed_recoverable')" in source
