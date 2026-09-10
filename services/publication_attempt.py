"""Recoverable publication: take ownership, act, verify, then record.

The problem this solves is not "publication can fail". It is that a worker
which dies mid-publication leaves no way to tell whether the document went
live. An exception is not evidence that activation failed - a timeout says
nothing about whether the write landed - so a retry that assumes failure can
republish content, and a retry that assumes success can leave a document
staged forever.

Three mechanisms, and they are separate on purpose:

*Idempotency* is `job_id:revision`. It answers "is this the same logical
publication", so a duplicate request for a revision already finished is a
no-op.

*Ownership* is a lease with a fencing token. The token is fresh for every
attempt. A second request may only take over an attempt whose lease has
expired, and it takes over by swapping the token - so of two requests racing
to recover the same job, exactly one wins. "The pointer does not name this
job yet" is NOT evidence the first worker died, and treating it as evidence
was a defect: two workers could then activate concurrently.

*Verification* asks what is actually visible. With
ADMIN_INGESTION_GENERATION_POINTER_ENABLED on, retrieval filters ingestion_id
to the rows of knowledge_active_generations (see
app/retrieval/opensearch_sections.py::_generation_filters), so the pointer is
the authority. With it off, visibility is the index itself, and the caller
supplies a verifier that counts active sections. Either way something is
checked; nothing is recorded as succeeded on the strength of no exception
having been raised.

Every write after the claim is fenced on the token, so a worker that lost its
lease cannot overwrite the outcome of the attempt that replaced it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable, Protocol

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from services.db import get_engine
from utils.logging import get_logger

LOGGER = get_logger("services.publication_attempt")

NOT_STARTED = "not_started"
IN_PROGRESS = "in_progress"
SUCCEEDED = "succeeded"
FAILED_RECOVERABLE = "failed_recoverable"

# How long an attempt may hold the job before another request may take it over.
# Long enough for a large document's activation, short enough that a dead
# worker does not block publication for an afternoon. A worker that exceeds it
# is not killed - it loses the right to record an outcome, which is what the
# fencing token enforces.
LEASE_SECONDS = 900


class PublicationConflict(Exception):
    """Another attempt owns this job, or the revision moved underneath it."""


class OwnershipLost(Exception):
    """This attempt's lease was taken over, so its writes were refused."""


@dataclass(frozen=True)
class AttemptRecord:
    """What is known about publication of one job."""

    job_id: str
    revision: str
    state: str
    attempt_key: str
    idempotency_key: str = ""
    detail: str = ""
    lease_expired: bool = True


@dataclass(frozen=True)
class Claim:
    """Ownership of one publication attempt.

    already_active says the generation was verified live before this attempt
    began - a previous attempt got that far and died. Activation is skipped and
    finalization is resumed, because an active pointer establishes visibility
    and says nothing about whether the bookkeeping after it completed.
    """

    job_id: str
    revision: str
    token: str
    already_active: bool = False


def idempotency_key(*, job_id: str, revision: str) -> str:
    """Identifies the logical publication, not the attempt.

    Bound to the revision, so an approval for different content cannot complete
    a publication started for this one: editing metadata changes the revision
    and therefore the key.
    """
    return f"{job_id}:{revision}"


class AttemptStore(Protocol):
    """The persistence publication needs, and nothing else."""

    def read(self, job_id: str) -> AttemptRecord: ...

    def claim(self, *, job_id: str, revision: str, token: str, idempotency: str) -> bool:
        """Take a fresh attempt. One conditional statement, never read-then-write."""

    def take_over(
        self, *, job_id: str, revision: str, token: str, previous_token: str, idempotency: str
    ) -> bool:
        """Take over an attempt whose lease expired, fencing on the token seen."""

    def settle(self, *, job_id: str, token: str, revision: str, state: str, detail: str) -> bool:
        """Record an outcome. False means this attempt no longer owns the job."""

    def active_ingestion_id(self, logical_document_id: str) -> str:
        """The authoritative visibility state, read fresh - never from cache."""


class PostgresAttemptStore:
    """The real store. Every method is one statement."""

    def read(self, job_id: str) -> AttemptRecord:
        with get_engine().connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT job_id, review_revision, publication_state,
                           publication_attempt_key, publication_idempotency_key,
                           publication_detail,
                           (publication_lease_expires_at IS NULL
                            OR publication_lease_expires_at < now()) AS lease_expired
                    FROM ingestion_jobs
                    WHERE job_id = :job_id
                    """
                ),
                {"job_id": job_id},
            ).mappings().first()
        if row is None:
            raise ValueError(f"Unknown ingestion job {job_id}.")
        return AttemptRecord(
            job_id=str(row["job_id"]),
            revision=str(row["review_revision"] or ""),
            state=str(row["publication_state"] or NOT_STARTED),
            attempt_key=str(row["publication_attempt_key"] or ""),
            idempotency_key=str(row["publication_idempotency_key"] or ""),
            detail=str(row["publication_detail"] or ""),
            lease_expired=bool(row["lease_expired"]),
        )

    def claim(self, *, job_id: str, revision: str, token: str, idempotency: str) -> bool:
        with get_engine().begin() as connection:
            result = connection.execute(
                text(
                    f"""
                    UPDATE ingestion_jobs
                    SET publication_state = 'in_progress',
                        publication_attempt_key = :token,
                        publication_idempotency_key = :idempotency,
                        publication_detail = '',
                        publication_attempted_at = now(),
                        publication_lease_expires_at
                            = now() + interval '{LEASE_SECONDS} seconds'
                    WHERE job_id = :job_id
                      AND review_revision = :revision
                      AND publication_state IN ('not_started', 'failed_recoverable')
                    """
                ),
                {
                    "job_id": job_id,
                    "revision": revision,
                    "token": token,
                    "idempotency": idempotency,
                },
            )
        return int(result.rowcount or 0) == 1

    def take_over(
        self, *, job_id: str, revision: str, token: str, previous_token: str, idempotency: str
    ) -> bool:
        # Two conditions carry this. The lease must have expired, so an attempt
        # that is merely slow is not stolen from. And the attempt key must
        # still be the one this caller saw, so of two requests recovering the
        # same job at the same moment, the first to swap the token wins and the
        # second matches nothing.
        with get_engine().begin() as connection:
            result = connection.execute(
                text(
                    f"""
                    UPDATE ingestion_jobs
                    SET publication_attempt_key = :token,
                        publication_idempotency_key = :idempotency,
                        publication_attempted_at = now(),
                        publication_lease_expires_at
                            = now() + interval '{LEASE_SECONDS} seconds'
                    WHERE job_id = :job_id
                      AND review_revision = :revision
                      AND publication_state = 'in_progress'
                      AND publication_attempt_key = :previous_token
                      AND publication_lease_expires_at IS NOT NULL
                      AND publication_lease_expires_at < now()
                    """
                ),
                {
                    "job_id": job_id,
                    "revision": revision,
                    "token": token,
                    "previous_token": previous_token,
                    "idempotency": idempotency,
                },
            )
        return int(result.rowcount or 0) == 1

    def settle(self, *, job_id: str, token: str, revision: str, state: str, detail: str) -> bool:
        # Fenced. A worker whose lease was taken over updates nothing, so it
        # cannot overwrite the outcome of the attempt that replaced it.
        with get_engine().begin() as connection:
            result = connection.execute(
                text(
                    """
                    UPDATE ingestion_jobs
                    SET publication_state = :state,
                        publication_detail = :detail,
                        publication_settled_at = now()
                    WHERE job_id = :job_id
                      AND review_revision = :revision
                      AND publication_attempt_key = :token
                    """
                ),
                {
                    "job_id": job_id,
                    "revision": revision,
                    "token": token,
                    "state": state,
                    "detail": detail[:500],
                },
            )
        return int(result.rowcount or 0) == 1

    def active_ingestion_id(self, logical_document_id: str) -> str:
        # Deliberately not services.knowledge_generations.active_generation_ids:
        # that reads a 15-second in-process cache, and recovery is asking what
        # is true now, not what was true when the cache filled.
        try:
            with get_engine().connect() as connection:
                value = connection.execute(
                    text(
                        """
                        SELECT active_ingestion_id
                        FROM knowledge_active_generations
                        WHERE logical_document_id = :logical_document_id
                        """
                    ),
                    {"logical_document_id": logical_document_id},
                ).scalar()
        except SQLAlchemyError:
            LOGGER.exception(
                "publication_visibility_lookup_failed",
                logical_document_id=logical_document_id,
            )
            # Not "" - that would read as "not published" and invite a retry
            # on a document that may well be live.
            raise
        return str(value or "")


def begin(
    store: AttemptStore,
    *,
    job_id: str,
    revision: str,
    logical_document_id: str,
    verify_visible: Callable[[], bool] | None = None,
) -> Claim | None:
    """Take ownership of a publication attempt, or explain why not.

    Returns None when this revision has already been published and finalized -
    a duplicate request is a no-op, not a second activation. Raises
    PublicationConflict when another attempt owns the job or the revision moved.

    verify_visible answers "is this generation live" for deployments with the
    generation pointer disabled, where the pointer cannot answer it. When it is
    None the pointer is the only authority consulted.
    """
    idempotency = idempotency_key(job_id=job_id, revision=revision)
    token = uuid.uuid4().hex
    current = store.read(job_id)

    if current.revision and current.revision != revision:
        raise PublicationConflict(
            "The document changed since this approval was given. Re-review it."
        )
    if current.state == SUCCEEDED and current.idempotency_key == idempotency:
        # Succeeded is written only after finalization, so this genuinely means
        # there is nothing left to do.
        LOGGER.info("publication_already_succeeded", correlation_id=job_id, revision=revision)
        return None
    if current.state == IN_PROGRESS:
        return _take_over(
            store,
            job_id=job_id,
            revision=revision,
            token=token,
            current=current,
            idempotency=idempotency,
            logical_document_id=logical_document_id,
            verify_visible=verify_visible,
        )
    if not store.claim(
        job_id=job_id, revision=revision, token=token, idempotency=idempotency
    ):
        raise PublicationConflict(
            "Another publication attempt is in progress for this document."
        )
    return Claim(job_id=job_id, revision=revision, token=token)


def _take_over(
    store: AttemptStore,
    *,
    job_id: str,
    revision: str,
    token: str,
    current: AttemptRecord,
    idempotency: str,
    logical_document_id: str,
    verify_visible: Callable[[], bool] | None,
) -> Claim:
    """An attempt is marked in progress. Decide whether this request may have it.

    Ownership first, outcome second. The previous version asked what happened
    and, seeing nothing live yet, proceeded - which let a second request
    activate while the original worker was still running. Not visible yet is
    not the same as dead.
    """
    if not current.lease_expired:
        raise PublicationConflict(
            "Another publication attempt is in progress for this document. "
            "Retry once it finishes or its lease expires."
        )
    if not store.take_over(
        job_id=job_id,
        revision=revision,
        token=token,
        previous_token=current.attempt_key,
        idempotency=idempotency,
    ):
        # Either the original worker settled it, or another recovery got here
        # first and swapped the token. Both mean this request does not own it.
        raise PublicationConflict(
            "Another request has taken over publication of this document."
        )

    # Ownership held. Only now is it safe to ask what the dead attempt achieved.
    live = _is_visible(
        store,
        job_id=job_id,
        logical_document_id=logical_document_id,
        verify_visible=verify_visible,
    )
    LOGGER.info(
        "publication_attempt_taken_over",
        correlation_id=job_id,
        logical_document_id=logical_document_id,
        already_active=live,
    )
    return Claim(job_id=job_id, revision=revision, token=token, already_active=live)


def _is_visible(
    store: AttemptStore,
    *,
    job_id: str,
    logical_document_id: str,
    verify_visible: Callable[[], bool] | None,
) -> bool:
    if verify_visible is not None:
        return bool(verify_visible())
    return store.active_ingestion_id(logical_document_id) == job_id


def confirm_visible(
    store: AttemptStore,
    *,
    job_id: str,
    claim: Claim,
    logical_document_id: str,
    verify_visible: Callable[[], bool] | None = None,
) -> None:
    """Check that activation actually took effect, before anything is recorded.

    Recording success because no exception was raised records a belief. This
    records an observation, and it is made in both deployments: the pointer
    when it is enabled, the index itself when it is not. An outcome that cannot
    be verified is never labelled succeeded.
    """
    if _is_visible(
        store,
        job_id=job_id,
        logical_document_id=logical_document_id,
        verify_visible=verify_visible,
    ):
        return
    fail(store, job_id=job_id, claim=claim, detail="not visible after activation")
    raise RuntimeError(
        "Publication did not take effect: this document is not visible after activation."
    )


def complete(store: AttemptStore, *, job_id: str, claim: Claim, detail: str) -> None:
    """Record success. Called only after every finalizing write has happened.

    Succeeded means finished, not activated. An active pointer establishes
    visibility and says nothing about whether the document record and job
    status were written, so recording success before them let a retry return
    early and leave the portal showing a half-published document.
    """
    if not store.settle(
        job_id=job_id,
        token=claim.token,
        revision=claim.revision,
        state=SUCCEEDED,
        detail=detail,
    ):
        raise OwnershipLost(
            "This publication attempt no longer owns the job, so its result was not recorded."
        )


def fail(store: AttemptStore, *, job_id: str, claim: Claim, detail: str) -> None:
    """Record a recoverable failure, so a retry knows an attempt happened."""
    try:
        owned = store.settle(
            job_id=job_id,
            token=claim.token,
            revision=claim.revision,
            state=FAILED_RECOVERABLE,
            detail=detail,
        )
    except Exception:
        # The attempt already failed; losing the record is better reported than
        # raised over the original cause. It stays in_progress, and recovery
        # takes it over once the lease expires - which is what in_progress
        # means.
        LOGGER.exception("publication_failure_not_recorded", correlation_id=job_id)
        return
    if not owned:
        LOGGER.warning(
            "publication_failure_not_recorded_ownership_lost", correlation_id=job_id
        )
