"""The review-storage migration, checked without a database.

These read the migration as text and check its shape. That is weaker than
applying it to Postgres and asserting the result, and it is what can be done
without a database, so what it does and does not establish is stated rather
than implied:

  established - the migration TEXT says what it should: statements carry IF NOT
                EXISTS, nothing is dropped or renamed, review_findings has no
                default, and the decisions table has the columns and constraint
                intended.
  NOT established - compatibility, repeatability, or that PostgreSQL accepts any
                of it. Reading SQL is not running it. Those claims are pending
                until tests/integration/test_review_migration_postgres.py has
                been executed against a real database, which has not happened.
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
    # Everything that existed before this one sorts earlier. Asserting it is
    # last would fail the moment a later migration is added, which says nothing
    # about whether this one runs.
    earlier = [name for name in migrations if name < MIGRATION.name]
    assert len(earlier) == migrations.index(MIGRATION.name)


def test_every_statement_carries_a_re_runnable_guard() -> None:
    """Checks the guard is written, which is not the same as proving repeatability.

    Repeat execution is proven by applying the migration three times to a real
    database, in the integration test. This only catches a statement that was
    written without a guard at all.
    """
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


def test_the_migration_creates_no_update_path_for_decisions() -> None:
    """Naming a table append-only does not enforce it.

    This checks only that the migration itself introduces no UPDATE or ON
    CONFLICT path. Whether the application ever updates or deletes a decision
    is a separate test, and whether the database permits it is a matter of
    grants - neither is established here.
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


def test_the_application_exposes_no_update_or_delete_for_decisions() -> None:
    """Append-only has to be enforced, not just asserted in a comment.

    Two layers are needed and only one is in this repository. This checks the
    first: no code writes an UPDATE or DELETE against the decisions table, so a
    decision cannot be edited or removed through the application.

    The second layer is database grants. If the application role holds UPDATE
    and DELETE on ingestion_review_decisions, then a bug, a migration or a
    console session can still rewrite history, and nothing in this repository
    prevents it. Revoking those grants is an infrastructure change and is
    recorded in the rollout notes as required rather than assumed.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    offenders = []
    for source in list((root / "services").rglob("*.py")) + list((root / "api").rglob("*.py")):
        text = source.read_text(encoding="utf-8", errors="replace")
        if "ingestion_review_decisions" not in text:
            continue
        for statement in ("UPDATE ingestion_review_decisions", "DELETE FROM ingestion_review_decisions"):
            if statement.lower() in text.lower():
                offenders.append(f"{source.name}: {statement}")

    assert offenders == [], offenders
