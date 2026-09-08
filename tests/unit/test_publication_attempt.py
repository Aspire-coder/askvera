"""Publication interrupted, and publication raced.

The store is faked so a failure can be injected exactly where it matters, and
so two requests can be interleaved deliberately. What that establishes is the
state machine's behaviour. Whether PostgreSQL makes the conditional statements
atomic is a database property, tested in
tests/integration/test_review_migration_postgres.py.
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
    Claim,
    OwnershipLost,
    PublicationConflict,
)

JOB = "job-1"
REVISION = "rev-a"
DOCUMENT = "country:DK:en:policy:company-policy"


class FakeStore:
    """An in-memory store whose conditional writes are genuinely conditional."""

    def __init__(
        self,
        *,
        state=NOT_STARTED,
        revision=REVISION,
        token="",
        idempotency="",
        pointer="",
        lease_expired=True,
    ):
        self.record = AttemptRecord(
            job_id=JOB,
            revision=revision,
            state=state,
            attempt_key=token,
            idempotency_key=idempotency,
            lease_expired=lease_expired,
        )
        self.pointer = pointer
        self.settled: list[tuple[str, str]] = []
        self.claims = 0
        self.take_overs = 0

    def read(self, job_id):
        return self.record

    def _replace(self, **changes):
        current = self.record
        self.record = AttemptRecord(
            job_id=current.job_id,
            revision=changes.get("revision", current.revision),
            state=changes.get("state", current.state),
            attempt_key=changes.get("attempt_key", current.attempt_key),
            idempotency_key=changes.get("idempotency_key", current.idempotency_key),
            detail=changes.get("detail", current.detail),
            lease_expired=changes.get("lease_expired", current.lease_expired),
        )

    def claim(self, *, job_id, revision, token, idempotency):
        self.claims += 1
        if self.record.revision != revision:
            return False
        if self.record.state not in (NOT_STARTED, FAILED_RECOVERABLE):
            return False
        self._replace(
            state=IN_PROGRESS,
            attempt_key=token,
            idempotency_key=idempotency,
            lease_expired=False,
        )
        return True

    def take_over(self, *, job_id, revision, token, previous_token, idempotency):
        self.take_overs += 1
        # Every condition the real statement carries.
        if self.record.revision != revision:
            return False
        if self.record.state != IN_PROGRESS:
            return False
        if self.record.attempt_key != previous_token:
            return False
        if not self.record.lease_expired:
            return False
        self._replace(attempt_key=token, idempotency_key=idempotency, lease_expired=False)
        return True

    def settle(self, *, job_id, token, revision, state, detail):
        if self.record.attempt_key != token or self.record.revision != revision:
            return False
        self.settled.append((state, detail))
        self._replace(state=state, detail=detail)
        return True

    def active_ingestion_id(self, logical_document_id):
        return self.pointer


def _begin(store, verify_visible=None):
    return attempt.begin(
        store,
        job_id=JOB,
        revision=REVISION,
        logical_document_id=DOCUMENT,
        verify_visible=verify_visible,
    )


def test_a_first_attempt_claims_the_job() -> None:
    store = FakeStore()
    claim = _begin(store)

    assert claim is not None
    assert claim.token
    assert claim.already_active is False


# --- ownership -------------------------------------------------------------


def test_a_live_worker_is_not_recovered_from() -> None:
    """The defect this replaced.

    A second request saw in_progress, found nothing visible yet, concluded the
    worker had died and proceeded - so two workers could activate at once. Not
    visible yet is not dead. Ownership is decided by the lease, before the
    question of what happened is even asked.
    """
    store = FakeStore(state=IN_PROGRESS, token="worker-1", lease_expired=False, pointer="")

    with pytest.raises(PublicationConflict):
        _begin(store)

    assert store.take_overs == 0
    assert store.record.attempt_key == "worker-1"


def test_an_expired_lease_may_be_taken_over() -> None:
    store = FakeStore(state=IN_PROGRESS, token="dead-worker", lease_expired=True, pointer="")

    claim = _begin(store)

    assert claim is not None
    assert claim.token != "dead-worker"
    assert claim.already_active is False


def test_only_one_of_two_simultaneous_recoveries_wins() -> None:
    """Both read the same dead attempt before either acts on it.

    The interleaving that matters: request B read the row, then request A took
    the attempt over and swapped the token, and only then does B try. B is
    fencing on a token that is no longer current, so its takeover matches
    nothing. Without the token in the WHERE clause both would succeed and both
    would activate.
    """
    store = FakeStore(state=IN_PROGRESS, token="dead-worker", lease_expired=True)
    # Both requests observed this row.
    observed = store.read(JOB)

    first = _begin(store)
    assert first is not None
    assert store.record.attempt_key == first.token

    with pytest.raises(PublicationConflict):
        attempt._take_over(
            store,
            job_id=JOB,
            revision=REVISION,
            token="second-request",
            current=observed,
            idempotency=attempt.idempotency_key(job_id=JOB, revision=REVISION),
            logical_document_id=DOCUMENT,
            verify_visible=None,
        )

    assert store.record.attempt_key == first.token, "the winner still owns it"


def test_a_stale_worker_cannot_overwrite_the_attempt_that_replaced_it() -> None:
    """Finding 2. settle() by job_id alone let a dead worker land its result."""
    store = FakeStore(state=IN_PROGRESS, token="dead-worker", lease_expired=True)
    stale = Claim(job_id=JOB, revision=REVISION, token="dead-worker")

    winner = _begin(store)
    assert winner is not None

    with pytest.raises(OwnershipLost):
        attempt.complete(store, job_id=JOB, claim=stale, detail="stale success")

    assert store.record.state == IN_PROGRESS
    assert store.settled == []


def test_a_stale_workers_failure_is_also_refused() -> None:
    """A dead worker must not mark a live attempt as failed either."""
    store = FakeStore(state=IN_PROGRESS, token="dead-worker", lease_expired=True)
    stale = Claim(job_id=JOB, revision=REVISION, token="dead-worker")

    assert _begin(store) is not None
    attempt.fail(store, job_id=JOB, claim=stale, detail="stale failure")

    assert store.record.state == IN_PROGRESS


# --- what a recovery finds -------------------------------------------------


def test_recovery_after_the_pointer_moved_resumes_finalization() -> None:
    """Finding 3. An active pointer is visibility, not completion.

    The previous version returned "already succeeded" here, so the document
    record and the job status were never written and the portal kept showing a
    published document as awaiting review.
    """
    store = FakeStore(state=IN_PROGRESS, token="dead-worker", lease_expired=True, pointer=JOB)

    claim = _begin(store)

    assert claim is not None
    assert claim.already_active is True
    assert store.settled == [], "nothing is recorded as succeeded before finalization"


def test_recovery_before_the_pointer_moved_redoes_the_activation() -> None:
    store = FakeStore(state=IN_PROGRESS, token="dead-worker", lease_expired=True, pointer="")

    claim = _begin(store)

    assert claim is not None
    assert claim.already_active is False


def test_a_duplicate_request_does_not_activate_a_second_time() -> None:
    store = FakeStore(
        state=SUCCEEDED,
        token="finished",
        idempotency=attempt.idempotency_key(job_id=JOB, revision=REVISION),
        pointer=JOB,
    )

    assert _begin(store) is None
    assert store.claims == 0
    assert store.take_overs == 0


def test_a_metadata_edit_invalidates_an_attempt_authorised_for_other_content() -> None:
    store = FakeStore(revision="rev-b")

    with pytest.raises(PublicationConflict) as raised:
        _begin(store)

    assert "changed since this approval" in str(raised.value)
    assert store.claims == 0


def test_the_idempotency_key_is_bound_to_the_revision() -> None:
    assert attempt.idempotency_key(job_id=JOB, revision="rev-a") != attempt.idempotency_key(
        job_id=JOB, revision="rev-b"
    )


def test_the_attempt_token_is_fresh_for_every_attempt() -> None:
    """Two attempts sharing a token cannot fence against each other."""
    first = _begin(FakeStore())
    second = _begin(FakeStore())

    assert first is not None and second is not None
    assert first.token != second.token


# --- verification ----------------------------------------------------------


def test_success_is_recorded_only_after_visibility_is_confirmed() -> None:
    store = FakeStore()
    claim = _begin(store)
    assert claim is not None
    store.pointer = JOB

    attempt.confirm_visible(
        store, job_id=JOB, claim=claim, logical_document_id=DOCUMENT
    )
    attempt.complete(store, job_id=JOB, claim=claim, detail="verified visible and finalized")

    assert store.record.state == SUCCEEDED


def test_activation_that_did_not_take_effect_is_reported_not_recorded_as_success() -> None:
    store = FakeStore(pointer="someone-else")
    claim = _begin(store)
    assert claim is not None

    with pytest.raises(RuntimeError):
        attempt.confirm_visible(
            store, job_id=JOB, claim=claim, logical_document_id=DOCUMENT
        )

    assert store.record.state == FAILED_RECOVERABLE


def test_without_a_pointer_visibility_is_verified_another_way() -> None:
    """Finding 4. "Succeeded, visibility unverified" is a contradiction.

    With the generation pointer disabled there is no pointer to read, so the
    caller supplies a verifier that counts active sections in the index. The
    outcome is verified, differently - not labelled a success with a caveat.
    """
    store = FakeStore(pointer="")
    claim = _begin(store, verify_visible=lambda: True)
    assert claim is not None

    attempt.confirm_visible(
        store,
        job_id=JOB,
        claim=claim,
        logical_document_id=DOCUMENT,
        verify_visible=lambda: True,
    )
    attempt.complete(store, job_id=JOB, claim=claim, detail="verified visible and finalized")

    assert store.record.state == SUCCEEDED
    assert "unverified" not in store.record.detail


def test_without_a_pointer_a_failed_verification_still_fails() -> None:
    store = FakeStore(pointer="")
    claim = _begin(store, verify_visible=lambda: False)
    assert claim is not None

    with pytest.raises(RuntimeError):
        attempt.confirm_visible(
            store,
            job_id=JOB,
            claim=claim,
            logical_document_id=DOCUMENT,
            verify_visible=lambda: False,
        )

    assert store.record.state == FAILED_RECOVERABLE


def test_no_state_is_ever_recorded_as_succeeded_but_unverified() -> None:
    """The phrase itself should not exist anywhere in the module."""
    import inspect

    source = inspect.getsource(attempt)
    assert "visibility unverified" not in source


def test_a_visibility_lookup_failure_is_not_read_as_unpublished() -> None:
    """Returning "" on error would invite a retry on a live document."""

    class Failing(FakeStore):
        def active_ingestion_id(self, logical_document_id):
            raise RuntimeError("database unreachable")

    store = Failing(state=IN_PROGRESS, token="dead-worker", lease_expired=True)
    with pytest.raises(RuntimeError):
        _begin(store)


# --- the shape of the real statements --------------------------------------


def test_the_claim_statement_is_conditional_in_one_write() -> None:
    import inspect

    source = inspect.getsource(attempt.PostgresAttemptStore.claim)
    assert "UPDATE ingestion_jobs" in source
    assert "AND review_revision = :revision" in source
    assert "publication_state IN ('not_started', 'failed_recoverable')" in source


def test_the_take_over_statement_checks_the_lease_and_fences_on_the_token() -> None:
    import inspect

    source = inspect.getsource(attempt.PostgresAttemptStore.take_over)
    assert "AND publication_attempt_key = :previous_token" in source
    assert "AND publication_lease_expires_at < now()" in source


def test_every_settle_is_bound_to_the_attempt_and_the_revision() -> None:
    import inspect

    source = inspect.getsource(attempt.PostgresAttemptStore.settle)
    assert "AND publication_attempt_key = :token" in source
    assert "AND review_revision = :revision" in source
    assert "rowcount" in source


def test_recovery_never_reads_the_cached_generation_lookup() -> None:
    """active_generation_ids caches for 15 seconds; recovery asks what is true now."""
    import inspect
    import re

    source = inspect.getsource(attempt.PostgresAttemptStore.active_ingestion_id)
    # Comments first. The comment here explains why the cached lookup is not
    # used, and matching the raw text found the explanation rather than a call.
    code = "\n".join(re.sub(r"#.*$", "", line) for line in source.splitlines())
    assert "active_generation_ids" not in code
    assert "knowledge_active_generations" in source
