"""The review-storage migration, checked without a database.

These read the migration as text and check its shape. That is weaker than
applying it to Postgres and asserting the result, and it is what can be done
without a database, so what it does and does not establish is stated rather
than implied:

  established - every statement is re-runnable, nothing is dropped or renamed,
                the previous application version keeps working, and a legacy
                job reads as unevaluated rather than clean.
  NOT established - that Postgres accepts it. It has never been executed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "20260908_01_ingestion_review_findings.sql"
)


def _statements() -> list[str]:
    """Statements with line comments removed, so a comment cannot be mistaken
    for SQL - which is exactly the mistake my first version of this made."""
    sql = MIGRATION.read_text(encoding="utf-8")
    stripped = "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())
    return [statement.strip() for statement in stripped.split(";") if statement.strip()]


def test_the_migration_exists_and_is_ordered_after_the_current_head() -> None:
    """Migrations apply in filename order, so a lower number would never run."""
    migrations = sorted(p.name for p in MIGRATION.parent.glob("*.sql"))
    assert MIGRATION.name in migrations
    assert migrations[-1] == MIGRATION.name


def test_every_statement_can_run_twice() -> None:
    """The deploy applies migrations on every run and a retry must be harmless."""
    for statement in _statements():
        upper = statement.upper()
        assert "IF NOT EXISTS" in upper or upper.startswith("COMMENT"), statement[:80]


def test_nothing_is_dropped_renamed_or_made_not_null() -> None:
    """Compatibility with the running application version.

    The previous version selects a fixed column list and writes through an
    allowlist. Adding nullable columns and a new table leaves it working
    untouched; dropping, renaming, or adding a NOT NULL column without a
    default would break it the moment the migration lands, which is before the
    new code is serving.
    """
    statements = " ".join(_statements()).upper()
    for forbidden in ("DROP COLUMN", "DROP TABLE", "RENAME", "ALTER COLUMN"):
        assert forbidden not in statements, forbidden

    # The one NOT NULL column carries a default, so existing rows are valid.
    assert "REVIEW_REVISION TEXT NOT NULL DEFAULT ''" in statements


def test_a_legacy_job_reads_as_unevaluated_not_as_clean() -> None:
    """The distinction that decides whether existing jobs publish unchecked.

    "No findings" and "never assessed" are different claims. If review_findings
    defaulted to an empty array, every job already in the table would assert
    that an assessment found nothing - and would publish on the strength of an
    assessment that never ran.
    """
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "ADD COLUMN IF NOT EXISTS review_findings JSONB;" in sql
    assert "review_findings JSONB NOT NULL" not in sql
    assert "review_findings JSONB DEFAULT" not in sql
    assert "ADD COLUMN IF NOT EXISTS review_evaluated_at TIMESTAMPTZ;" in sql


def test_decisions_are_append_only_with_no_update_path() -> None:
    """History, not current state.

    Overwriting the previous approval destroys the record of who approved what,
    which is the thing an audit asks for. A later decision adds a row.
    """
    # Comments are stripped first. Checking the raw text matched the word
    # "UPDATE" inside a comment explaining that there is no UPDATE path, which
    # is the same mistake that broke the idempotency check earlier.
    statements = " ".join(_statements()).upper()
    assert "CREATE TABLE IF NOT EXISTS INGESTION_REVIEW_DECISIONS" in statements
    assert "ON CONFLICT" not in statements
    assert "UPDATE" not in statements


@pytest.mark.parametrize(
    "column",
    ["job_id", "review_revision", "decided_by", "decision", "reason", "decided_at"],
)
def test_a_decision_records_who_what_why_and_when(column: str) -> None:
    assert column in MIGRATION.read_text(encoding="utf-8")


def test_a_decision_value_is_constrained() -> None:
    """A free-text decision column drifts into 'approved', 'ok', 'yes'."""
    assert "CHECK (decision IN ('publish', 'reject'))" in MIGRATION.read_text(encoding="utf-8")


def test_the_lookup_index_matches_the_only_access_pattern() -> None:
    """Publication asks for the newest decision on one job and revision."""
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "(job_id, review_revision, decided_at DESC)" in sql


def test_no_finding_gets_its_own_table() -> None:
    """Findings are replaced wholesale when a document is reassessed, so a row
    per finding would be deleted and rewritten every time and buy nothing."""
    statements = " ".join(_statements()).upper()
    assert statements.count("CREATE TABLE") == 1
