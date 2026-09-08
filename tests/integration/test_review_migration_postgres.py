"""Execute the review migration against a real PostgreSQL, when one exists.

The unit tests read the migration as text. Text checks establish shape and
nothing about whether PostgreSQL accepts the statements, whether they are
genuinely repeatable, or whether the previous application version keeps working
against the migrated schema. Only running them does that.

These tests skip unless ASKVERA_TEST_POSTGRES_URL points at a disposable
database. They must never be pointed at the live database: they create and drop
schemas.

    createdb askvera_migration_test
    ASKVERA_TEST_POSTGRES_URL=postgresql://localhost/askvera_migration_test \\
        python -m pytest tests/integration/test_review_migration_postgres.py

Status where this was written: skipped. No psql, no reachable Docker daemon and
no testing.postgresql, so the migration has never been executed anywhere.
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("ASKVERA_TEST_POSTGRES_URL"),
    reason="ASKVERA_TEST_POSTGRES_URL is not set; migration has not been executed",
)

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "20260908_01_ingestion_review_findings.sql"
)

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

    engine = create_engine(os.environ["ASKVERA_TEST_POSTGRES_URL"], future=True)
    name = f"review_migration_{uuid.uuid4().hex[:12]}"
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{name}"'))
    try:
        yield engine, name
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{name}" CASCADE'))


def _apply(connection, name: str) -> None:
    from sqlalchemy import text

    connection.execute(text(f'SET search_path TO "{name}"'))
    sql = MIGRATION.read_text(encoding="utf-8")
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
