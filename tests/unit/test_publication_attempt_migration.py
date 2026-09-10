"""The publication-attempt migration, read as text.

Same limits as the review migration's text checks, stated rather than implied:
this establishes what the SQL says, not that PostgreSQL accepts it, that it is
repeatable, or that the running version survives it. Those are pending until
the integration tests execute against a real database.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
MIGRATION = MIGRATIONS_DIR / "20260908_02_publication_attempt.sql"
LEASE_MIGRATION = MIGRATIONS_DIR / "20260908_03_publication_lease.sql"


def _statements(path: Path = MIGRATION) -> list[str]:
    sql = path.read_text(encoding="utf-8")
    stripped = "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())
    return [statement.strip() for statement in stripped.split(";") if statement.strip()]


@pytest.mark.parametrize("path", [MIGRATION, LEASE_MIGRATION])
def test_every_statement_carries_a_re_runnable_guard(path) -> None:
    for statement in _statements(path):
        upper = statement.upper()
        assert "IF NOT EXISTS" in upper or upper.startswith("COMMENT"), statement[:80]


@pytest.mark.parametrize("path", [MIGRATION, LEASE_MIGRATION])
def test_nothing_is_dropped_renamed_or_altered(path) -> None:
    """The previous version keeps working while this lands."""
    statements = " ".join(_statements(path)).upper()
    for forbidden in ("DROP COLUMN", "DROP TABLE", "RENAME", "ALTER COLUMN"):
        assert forbidden not in statements, forbidden


@pytest.mark.parametrize("path", [MIGRATION, LEASE_MIGRATION])
def test_every_not_null_column_carries_a_default(path) -> None:
    """A NOT NULL column without a default breaks existing rows immediately."""
    for statement in _statements(path):
        upper = statement.upper()
        if "NOT NULL" in upper and upper.startswith("ALTER TABLE"):
            assert "DEFAULT" in upper, statement[:120]


def test_existing_rows_read_as_not_started() -> None:
    """Jobs that published before this column existed are already 'ready'.

    not_started is right for them: publication refuses anything that is not
    ready_for_review, so the default cannot invite a republication.
    """
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "publication_state TEXT NOT NULL DEFAULT 'not_started'" in sql


def test_the_attempt_key_is_documented_as_revision_bound() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "job_id:review_revision" in sql


def test_the_lease_is_nullable_so_an_old_attempt_reads_as_expired() -> None:
    """A NULL lease must mean "no owner can still be running".

    Defaulting it to a future time would make every attempt recorded before
    leases existed look live, and block recovery until it passed.
    """
    sql = LEASE_MIGRATION.read_text(encoding="utf-8")

    assert "publication_lease_expires_at TIMESTAMPTZ;" in sql
    assert "publication_lease_expires_at TIMESTAMPTZ NOT NULL" not in sql
    assert "publication_lease_expires_at TIMESTAMPTZ DEFAULT" not in sql


def test_the_idempotency_key_is_separate_from_the_attempt_key() -> None:
    """One key doing both jobs was the concurrency defect.

    If the attempt key is job_id:revision, two requests recovering the same job
    compute the same token and neither can fence against the other.
    """
    sql = LEASE_MIGRATION.read_text(encoding="utf-8")

    assert "publication_idempotency_key TEXT NOT NULL DEFAULT ''" in sql
    assert "fencing token" in sql
