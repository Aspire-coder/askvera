"""Recoverable publication: begin an attempt, act, then record what happened.

The problem this solves is not "publication can fail". It is that a worker
which dies mid-publication leaves no way to tell whether the document went
live. An exception is not evidence that activation failed - a timeout says
nothing about whether the write landed - so a retry that assumes failure can
republish content, and a retry that assumes success can leave a document
staged forever.

The answer is to make one step authoritative and then ASK IT. With
ADMIN_INGESTION_GENERATION_POINTER_ENABLED on, retrieval filters ingestion_id
to the rows of knowledge_active_generations (see
app/retrieval/opensearch_sections.py::_generation_filters), so the pointer
update is the commit point: everything before it is invisible, and the pointer
itself is a single-row write under an advisory lock. Recovery therefore reads
the pointer rather than reasoning about the exception.

The database access sits behind AttemptStore so the failure points can be
tested without PostgreSQL. The default implementation is the real one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from services.db import get_engine
from utils.logging import get_logger

LOGGER = get_logger("services.publication_attempt")

NOT_STARTED = "not_started"
IN_PROGRESS = "in_progress"
SUCCEEDED = "succeeded"
FAILED_RECOVERABLE = "failed_recoverable"


class PublicationConflict(Exception):
    """Another attempt holds this job, or the revision moved underneath it."""


@dataclass(frozen=True)
class AttemptRecord:
    """What is known about publication of one job at one revision."""

    job_id: str
    revision: str
    state: str
    attempt_key: str
    detail: str = ""

    @property
    def is_settled(self) -> bool:
        return self.state == SUCCEEDED


def attempt_key(*, job_id: str, revision: str) -> str:
    """Idempotency key.

    Bound to the revision, so an approval for different content cannot complete
    an attempt started for this one: editing metadata changes the revision and
    therefore the key.
    """
    return f"{job_id}:{revision}"


class AttemptStore(Protocol):
    """The persistence publication needs, and nothing else."""

    def read(self, job_id: str) -> AttemptRecord: ...

    def claim(self, *, job_id: str, revision: str, key: str) -> bool:
        """Move to in_progress only from a state that permits a new attempt.

        Returns False when another attempt holds the job or the revision has
        changed. Must be a single conditional statement, not read-then-write.
        """

    def settle(self, *, job_id: str, state: str, detail: str) -> None: ...

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
                           publication_attempt_key, publication_detail
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
            detail=str(row["publication_detail"] or ""),
        )

    def claim(self, *, job_id: str, revision: str, key: str) -> bool:
        # One conditional UPDATE. Reading the state and then writing it would
        # let two workers both read 'not_started' and both proceed.
        with get_engine().begin() as connection:
            result = connection.execute(
                text(
                    """
                    UPDATE ingestion_jobs
                    SET publication_state = 'in_progress',
                        publication_attempt_key = :key,
                        publication_detail = '',
                        publication_attempted_at = now()
                    WHERE job_id = :job_id
                      AND review_revision = :revision
                      AND publication_state IN ('not_started', 'failed_recoverable')
                    """
                ),
                {"job_id": job_id, "revision": revision, "key": key},
            )
        return int(result.rowcount or 0) == 1

    def settle(self, *, job_id: str, state: str, detail: str) -> None:
        with get_engine().begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE ingestion_jobs
                    SET publication_state = :state,
                        publication_detail = :detail,
                        publication_settled_at = now()
                    WHERE job_id = :job_id
                    """
                ),
                {"job_id": job_id, "state": state, "detail": detail[:500]},
            )

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
) -> AttemptRecord | None:
    """Claim the right to publish, or explain why this attempt should not run.

    Returns None when the job is already published - a duplicate request is a
    no-op, not a second activation. Raises PublicationConflict when another
    attempt holds the job or the revision has moved.
    """
    key = attempt_key(job_id=job_id, revision=revision)
    current = store.read(job_id)

    if current.revision and current.revision != revision:
        raise PublicationConflict(
            "The document changed since this approval was given. Re-review it."
        )
    if current.state == SUCCEEDED and current.attempt_key == key:
        LOGGER.info("publication_already_succeeded", correlation_id=job_id, revision=revision)
        return None
    if current.state == IN_PROGRESS:
        # The interesting case. Ask the authority instead of guessing.
        return _resolve_in_progress(
            store,
            job_id=job_id,
            revision=revision,
            key=key,
            logical_document_id=logical_document_id,
        )
    if not store.claim(job_id=job_id, revision=revision, key=key):
        raise PublicationConflict(
            "Another publication attempt is in progress for this document."
        )
    return AttemptRecord(job_id=job_id, revision=revision, state=IN_PROGRESS, attempt_key=key)


def _resolve_in_progress(
    store: AttemptStore,
    *,
    job_id: str,
    revision: str,
    key: str,
    logical_document_id: str,
) -> AttemptRecord | None:
    """An attempt is marked in progress. Find out whether it actually landed.

    This is the whole point of the design. A worker killed between activating
    sections and moving the pointer leaves exactly the same row as a worker
    killed after moving it, and only the pointer distinguishes them.
    """
    live = store.active_ingestion_id(logical_document_id)
    if live == job_id:
        # It published. The previous attempt died before it could say so.
        LOGGER.info(
            "publication_recovered_as_succeeded",
            correlation_id=job_id,
            logical_document_id=logical_document_id,
        )
        store.settle(job_id=job_id, state=SUCCEEDED, detail="recovered: pointer already active")
        return None

    if key and store.read(job_id).attempt_key != key:
        # A different revision's attempt holds the row.
        raise PublicationConflict(
            "Another publication attempt is in progress for this document."
        )
    LOGGER.info(
        "publication_resuming_unfinished_attempt",
        correlation_id=job_id,
        logical_document_id=logical_document_id,
        observed_active=live,
    )
    # Not visible, so nothing a reader can see is half-done. Safe to redo.
    return AttemptRecord(job_id=job_id, revision=revision, state=IN_PROGRESS, attempt_key=key)


def confirm(
    store: AttemptStore,
    *,
    job_id: str,
    logical_document_id: str,
    pointer_enabled: bool,
) -> None:
    """Verify the authoritative visibility state, then record success.

    Recording success on the strength of "no exception was raised" records a
    belief. Reading the pointer records an observation.
    """
    if not pointer_enabled:
        # Without the pointer there is no authority to consult: visibility is
        # whatever the index holds, and this path has no commit point. Say so
        # rather than record a confirmation that was never made.
        store.settle(
            job_id=job_id,
            state=SUCCEEDED,
            detail="published without generation pointer; visibility unverified",
        )
        LOGGER.warning("publication_unverified_no_pointer", correlation_id=job_id)
        return

    live = store.active_ingestion_id(logical_document_id)
    if live != job_id:
        store.settle(
            job_id=job_id,
            state=FAILED_RECOVERABLE,
            detail=f"pointer names {live or 'nothing'} after activation",
        )
        raise RuntimeError(
            "Publication did not take effect: the active generation is "
            f"{live or 'unset'}, not this document."
        )
    store.settle(job_id=job_id, state=SUCCEEDED, detail="pointer confirmed")


def fail(store: AttemptStore, *, job_id: str, detail: str) -> None:
    """Record a recoverable failure, so a retry knows an attempt happened."""
    try:
        store.settle(job_id=job_id, state=FAILED_RECOVERABLE, detail=detail)
    except Exception:
        # The attempt already failed; losing the record is worse reported than
        # raised over the original cause. It stays in_progress, and recovery
        # inspects the pointer - which is exactly what in_progress means.
        LOGGER.exception("publication_failure_not_recorded", correlation_id=job_id)
