"""Execute the review and publication migrations against a real PostgreSQL.

The unit tests read the migration as text. Text checks establish shape and
nothing about whether PostgreSQL accepts the statements, whether they are
genuinely repeatable, or whether the previous application version keeps working
against the migrated schema. Only running them does that.

These tests skip unless a database is designated disposable twice over:
ASKVERA_TEST_POSTGRES_URL names it and ASKVERA_TEST_POSTGRES_DISPOSABLE=yes
confirms it is expendable. They never fall back to the application's own
database configuration, and they refuse outright to run against a URL matching
the configured RDS host or one that looks managed. They create and drop
schemas, and the drop is scoped to a generated name they created themselves.

Two variables reduce accidental targeting. They do not prevent someone
supplying the wrong values: both can be set, deliberately, to a database
somebody believes is disposable and is not. The refusal check narrows it
further and is not a guarantee either - it recognises the database this
application is configured for, not every database that matters.

    createdb askvera_migration_test
    ASKVERA_TEST_POSTGRES_URL=postgresql://localhost/askvera_migration_test \\
        python -m pytest tests/integration/test_review_migration_postgres.py

Status where this was written: skipped. No psql, no reachable Docker daemon and
no testing.postgresql, so neither migration has been executed anywhere. Skipped
tests are not evidence of safety, and this remains a release blocker.
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

import pytest

# The database must be designated disposable, twice over, and must never be
# reached by falling back to the application's own configuration.
#
# ASKVERA_TEST_POSTGRES_URL names it, and ASKVERA_TEST_POSTGRES_DISPOSABLE must
# be set to "yes" as a separate deliberate act. Two variables rather than one
# because a URL can be pasted from a runbook by accident; a second variable
# saying "this database is expendable" cannot be set by accident.
_URL = os.environ.get("ASKVERA_TEST_POSTGRES_URL", "")
_DISPOSABLE = os.environ.get("ASKVERA_TEST_POSTGRES_DISPOSABLE", "").strip().lower() == "yes"

pytestmark = pytest.mark.skipif(
    not (_URL and _DISPOSABLE),
    reason=(
        "migration not executed: set ASKVERA_TEST_POSTGRES_URL and "
        "ASKVERA_TEST_POSTGRES_DISPOSABLE=yes for a throwaway database"
    ),
)


def _refuse_live_database(url: str) -> None:
    """Stop before touching anything that looks like a real database.

    These tests create and drop schemas. Running them against the application's
    database would destroy data, and the way that happens is never a decision -
    it is an environment variable left set from something else.
    """
    from config import settings

    for attribute in ("RDS_HOST", "RDS_DB_IDENTIFIER"):
        live = str(getattr(settings, attribute, "") or "").strip()
        if live and live.lower() in url.lower():
            raise RuntimeError(
                f"ASKVERA_TEST_POSTGRES_URL names {attribute} from the application "
                "configuration. These tests create and drop schemas and must never "
                "run against it."
            )
    if any(marker in url.lower() for marker in ("prod", "rds.amazonaws.com")):
        raise RuntimeError(
            "ASKVERA_TEST_POSTGRES_URL looks like a managed or production database. "
            "Use a local throwaway instance."
        )


MIGRATIONS = [
    Path(__file__).resolve().parents[2] / "migrations" / name
    for name in (
        "20260908_01_ingestion_review_findings.sql",
        "20260908_02_publication_attempt.sql",
    )
]

# The columns the previous application version selects. If the migration breaks
# any of them, the running version fails the moment it lands - which is before
# the new code is serving.
PREVIOUS_VERSION_COLUMNS = (
    "job_id, filename, country, language, document_type, access_scope, "
    "document_version, status, progress, section_count, source_uri, upload_uri, "
    "content_hash, accepted_by, review_before_publish, logical_document_id, "
    "document_owner, approval_reference, effective_date, expiry_date, "
    "malware_scan_status, attempt_count, error_message, created_at, updated_at"
)

# A realistic pre-migration table: what a legacy row looks like before any
# review column exists.
LEGACY_SCHEMA = """
CREATE TABLE ingestion_jobs (
    job_id TEXT PRIMARY KEY,
    filename TEXT NOT NULL DEFAULT '',
    country TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT '',
    document_type TEXT NOT NULL DEFAULT '',
    access_scope TEXT NOT NULL DEFAULT 'country',
    document_version TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'queued',
    progress INTEGER NOT NULL DEFAULT 0,
    section_count INTEGER NOT NULL DEFAULT 0,
    source_uri TEXT NOT NULL DEFAULT '',
    upload_uri TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL DEFAULT '',
    accepted_by TEXT NOT NULL DEFAULT '',
    review_before_publish BOOLEAN NOT NULL DEFAULT TRUE,
    logical_document_id TEXT NOT NULL DEFAULT '',
    document_owner TEXT NOT NULL DEFAULT '',
    approval_reference TEXT NOT NULL DEFAULT '',
    effective_date DATE,
    expiry_date DATE,
    malware_scan_status TEXT NOT NULL DEFAULT 'not_required',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


@pytest.fixture()
def schema():
    """A disposable schema per test, dropped afterwards whatever happens."""
    from sqlalchemy import create_engine, text

    _refuse_live_database(_URL)
    engine = create_engine(_URL, future=True)
    # A generated name, so cleanup can only ever drop a schema this test made.
    name = f"review_migration_{uuid.uuid4().hex[:12]}"
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{name}"'))
    try:
        yield engine, name
    finally:
        with engine.begin() as connection:
            # Scoped to the generated name. Nothing else is dropped, and the
            # public schema is never touched.
            assert name.startswith("review_migration_")
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{name}" CASCADE'))


def _apply(connection, name: str) -> None:
    """Apply both migrations in filename order, as the deploy does."""
    from sqlalchemy import text

    connection.execute(text(f'SET search_path TO "{name}"'))
    for migration in MIGRATIONS:
        sql = migration.read_text(encoding="utf-8")
        stripped = "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())
        for statement in (s.strip() for s in stripped.split(";")):
            if statement:
                connection.execute(text(statement))


def test_the_migration_applies_to_a_legacy_table_holding_rows(schema) -> None:
    """The case that matters: existing jobs, not an empty table."""
    from sqlalchemy import text

    engine, name = schema
    with engine.begin() as connection:
        connection.execute(text(f'SET search_path TO "{name}"'))
        connection.execute(text(LEGACY_SCHEMA))
        connection.execute(
            text(
                "INSERT INTO ingestion_jobs (job_id, filename, status, document_version) "
                "VALUES ('legacy-1', 'UK-EN-Company-Policy.pdf', 'ready', '2026-01')"
            )
        )
        _apply(connection, name)

        row = connection.execute(
            text(
                "SELECT review_revision, review_findings, review_evaluated_at "
                "FROM ingestion_jobs WHERE job_id = 'legacy-1'"
            )
        ).mappings().one()

    # Unevaluated, not clean. An empty findings array would assert an
    # assessment that never ran.
    assert row["review_findings"] is None
    assert row["review_evaluated_at"] is None
    assert row["review_revision"] == ""


def test_the_migration_is_repeatable(schema) -> None:
    """The deploy applies migrations on every run, and retries happen."""
    from sqlalchemy import text

    engine, name = schema
    with engine.begin() as connection:
        connection.execute(text(f'SET search_path TO "{name}"'))
        connection.execute(text(LEGACY_SCHEMA))
        _apply(connection, name)
        _apply(connection, name)
        _apply(connection, name)

        count = connection.execute(
            text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_schema = :schema AND table_name = 'ingestion_jobs' "
                "AND column_name = 'review_revision'"
            ),
            {"schema": name},
        ).scalar_one()

    assert count == 1


def test_the_previous_application_version_still_reads_every_column(schema) -> None:
    """Compatibility with the code that is serving while the migration lands."""
    from sqlalchemy import text

    engine, name = schema
    with engine.begin() as connection:
        connection.execute(text(f'SET search_path TO "{name}"'))
        connection.execute(text(LEGACY_SCHEMA))
        connection.execute(
            text("INSERT INTO ingestion_jobs (job_id) VALUES ('legacy-2')")
        )
        _apply(connection, name)

        row = connection.execute(
            text(f"SELECT {PREVIOUS_VERSION_COLUMNS} FROM ingestion_jobs WHERE job_id = 'legacy-2'")
        ).mappings().one()

    assert row["job_id"] == "legacy-2"


def test_a_decision_row_round_trips_and_the_constraint_holds(schema) -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    engine, name = schema
    with engine.begin() as connection:
        connection.execute(text(f'SET search_path TO "{name}"'))
        connection.execute(text(LEGACY_SCHEMA))
        _apply(connection, name)
        connection.execute(
            text(
                "INSERT INTO ingestion_review_decisions "
                "(decision_id, job_id, review_revision, decided_by, decision, reason) "
                "VALUES ('d1', 'job-1', 'rev-1', 'reviewer@example.com', 'publish', 'Checked.')"
            )
        )
        stored = connection.execute(
            text("SELECT decision, decided_at FROM ingestion_review_decisions WHERE decision_id='d1'")
        ).mappings().one()

    assert stored["decision"] == "publish"
    # Server-generated, not supplied by the caller.
    assert stored["decided_at"] is not None

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(text(f'SET search_path TO "{name}"'))
            connection.execute(
                text(
                    "INSERT INTO ingestion_review_decisions "
                    "(decision_id, job_id, review_revision, decided_by, decision, reason) "
                    "VALUES ('d2', 'job-1', 'rev-1', 'r@example.com', 'approved', 'x')"
                )
            )


def test_two_decisions_for_one_revision_both_survive(schema) -> None:
    """Append-only in practice: a later decision must not replace an earlier one."""
    from sqlalchemy import text

    engine, name = schema
    with engine.begin() as connection:
        connection.execute(text(f'SET search_path TO "{name}"'))
        connection.execute(text(LEGACY_SCHEMA))
        _apply(connection, name)
        for identifier, decision in (("d1", "reject"), ("d2", "publish")):
            connection.execute(
                text(
                    "INSERT INTO ingestion_review_decisions "
                    "(decision_id, job_id, review_revision, decided_by, decision, reason) "
                    "VALUES (:id, 'job-1', 'rev-1', 'r@example.com', :decision, 'reason')"
                ),
                {"id": identifier, "decision": decision},
            )
        rows = connection.execute(
            text("SELECT decision FROM ingestion_review_decisions WHERE job_id='job-1'")
        ).scalars().all()

    assert sorted(rows) == ["publish", "reject"]


def test_a_legacy_job_reads_as_never_attempted(schema) -> None:
    """not_started is right for a job that published before this existed.

    Publication refuses anything that is not ready_for_review, so the default
    cannot invite a republication of something already out.
    """
    from sqlalchemy import text

    engine, name = schema
    with engine.begin() as connection:
        connection.execute(text(f'SET search_path TO "{name}"'))
        connection.execute(text(LEGACY_SCHEMA))
        connection.execute(
            text("INSERT INTO ingestion_jobs (job_id, status) VALUES ('legacy-3', 'ready')")
        )
        _apply(connection, name)
        row = connection.execute(
            text(
                "SELECT publication_state, publication_attempt_key, "
                "publication_attempted_at FROM ingestion_jobs WHERE job_id = 'legacy-3'"
            )
        ).mappings().one()

    assert row["publication_state"] == "not_started"
    assert row["publication_attempt_key"] == ""
    assert row["publication_attempted_at"] is None


def test_the_conditional_claim_lets_exactly_one_of_two_workers_through(schema) -> None:
    """The property the whole concurrency design rests on.

    Two sessions issue the same conditional UPDATE against one job. If both
    report a row, two workers publish the same document at once. This is a
    database behaviour and cannot be established by a fake store.
    """
    from sqlalchemy import text

    engine, name = schema
    claim = text(
        """
        UPDATE ingestion_jobs
        SET publication_state = 'in_progress', publication_attempt_key = :key
        WHERE job_id = 'job-1'
          AND review_revision = 'rev-a'
          AND publication_state IN ('not_started', 'failed_recoverable')
        """
    )
    with engine.begin() as connection:
        connection.execute(text(f'SET search_path TO "{name}"'))
        connection.execute(text(LEGACY_SCHEMA))
        _apply(connection, name)
        connection.execute(
            text(
                "INSERT INTO ingestion_jobs (job_id, status, review_revision) "
                "VALUES ('job-1', 'ready_for_review', 'rev-a')"
            )
        )

    claimed = []
    for key in ("first", "second"):
        with engine.begin() as connection:
            connection.execute(text(f'SET search_path TO "{name}"'))
            claimed.append(connection.execute(claim, {"key": key}).rowcount)

    assert claimed == [1, 0]


def test_a_findings_document_round_trips_as_jsonb(schema) -> None:
    """The application writes JSON text with an explicit cast."""
    from sqlalchemy import text

    engine, name = schema
    with engine.begin() as connection:
        connection.execute(text(f'SET search_path TO "{name}"'))
        connection.execute(text(LEGACY_SCHEMA))
        _apply(connection, name)
        connection.execute(
            text("INSERT INTO ingestion_jobs (job_id) VALUES ('job-2')")
        )
        connection.execute(
            text(
                "UPDATE ingestion_jobs SET review_findings = CAST(:findings AS JSONB) "
                "WHERE job_id = 'job-2'"
            ),
            {
                "findings": (
                    '{"schema": 1, "findings": [{"field": "expiry_date", '
                    '"severity": "contradiction", "detail": "x"}], "uncertain_pages": [4]}'
                )
            },
        )
        stored = connection.execute(
            text(
                "SELECT review_findings -> 'uncertain_pages' AS pages "
                "FROM ingestion_jobs WHERE job_id = 'job-2'"
            )
        ).scalar_one()

    assert list(stored) == [4]
