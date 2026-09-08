"""The publication-attempt migration, read as text.

Same limits as the review migration's text checks, stated rather than implied:
this establishes what the SQL says, not that PostgreSQL accepts it, that it is
repeatable, or that the running version survives it. Those are pending until
the integration tests execute against a real database.
"""

from __future__ import annotations

import re
from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "20260908_02_publication_attempt.sql"
)


def _statements() -> list[str]:
    sql = MIGRATION.read_text(encoding="utf-8")
    stripped = "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())
    return [statement.strip() for statement in stripped.split(";") if statement.strip()]


def test_every_statement_carries_a_re_runnable_guard() -> None:
    for statement in _statements():
        upper = statement.upper()
        assert "IF NOT EXISTS" in upper or upper.startswith("COMMENT"), statement[:80]


def test_nothing_is_dropped_renamed_or_altered() -> None:
    """The previous version keeps working while this lands."""
    statements = " ".join(_statements()).upper()
    for forbidden in ("DROP COLUMN", "DROP TABLE", "RENAME", "ALTER COLUMN"):
        assert forbidden not in statements, forbidden


def test_every_not_null_column_carries_a_default() -> None:
    """A NOT NULL column without a default breaks existing rows immediately."""
    for statement in _statements():
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
