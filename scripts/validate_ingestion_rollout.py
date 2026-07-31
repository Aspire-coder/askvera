"""Validate controlled-ingestion readiness without changing deployed state."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError
from opensearchpy.exceptions import OpenSearchException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings  # noqa: E402
from scripts.backfill_active_generation_pointers import (  # noqa: E402
    existing_pointers,
    generation_candidates,
    load_active_records,
    pointer_coverage_failures,
)
from scripts.ingestion.load_policy_sections_to_opensearch import _client  # noqa: E402
from scripts.run_db_migrations import apply_migrations  # noqa: E402
from scripts.validate_config import validate  # noqa: E402
from services.aws_clients import init_aws_clients  # noqa: E402
from services.db import close_db, get_engine, init_db  # noqa: E402
from utils.logging import configure_logging  # noqa: E402
from utils.opensearch_fields import has_exact_keyword_mapping  # noqa: E402

REQUIRED_JOB_COLUMNS = {
    "logical_document_id",
    "document_owner",
    "approval_reference",
    "effective_date",
}
REQUIRED_DOCUMENT_COLUMNS = set(REQUIRED_JOB_COLUMNS)
REQUIRED_TABLES = {
    "knowledge_active_generations",
    "knowledge_document_generations",
}


def database_failures() -> list[str]:
    """Return missing schema prerequisites for controlled publication."""
    failures: list[str] = []
    with get_engine().connect() as connection:
        table_rows = connection.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                      'knowledge_active_generations',
                      'knowledge_document_generations'
                  )
                """
            )
        ).scalars()
        tables = set(table_rows)
        for table in sorted(REQUIRED_TABLES - tables):
            failures.append(f"missing database table: {table}")

        for table, required in (
            ("ingestion_jobs", REQUIRED_JOB_COLUMNS),
            ("knowledge_documents", REQUIRED_DOCUMENT_COLUMNS),
        ):
            columns = set(
                connection.execute(
                    text(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = :table_name
                        """
                    ),
                    {"table_name": table},
                ).scalars()
            )
            for column in sorted(required - columns):
                failures.append(f"missing database column: {table}.{column}")
    return failures


def opensearch_failures() -> list[str]:
    """Return missing index mapping prerequisites for generation filtering."""
    mapping = _client().indices.get_mapping(index=settings.OPENSEARCH_INDEX)
    index_mapping = mapping.get(settings.OPENSEARCH_INDEX)
    if index_mapping is None and len(mapping) == 1:
        index_mapping = next(iter(mapping.values()))
    properties = (
        (index_mapping or {})
        .get("mappings", {})
        .get("properties", {})
    )
    field = properties.get("logical_document_id", {})
    if not has_exact_keyword_mapping(field):
        return [
            "OpenSearch logical_document_id must provide an exact keyword mapping"
        ]
    ingestion = properties.get("ingestion_id", {})
    if not has_exact_keyword_mapping(ingestion):
        return ["OpenSearch ingestion_id must provide an exact keyword mapping"]
    return []


def generation_coverage_failures() -> list[str]:
    """Require one exact database pointer for every live search generation."""
    pointers = existing_pointers()
    candidates = generation_candidates(
        load_active_records(),
        pointers=pointers,
    )
    if not candidates:
        return ["OpenSearch has no active knowledge generations"]
    return pointer_coverage_failures(candidates, pointers)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--load-ssm", action="store_true")
    args = parser.parse_args()

    configure_logging()
    if args.load_ssm:
        settings.load_ssm_config()
    failures = [f"configuration: {item}" for item in validate()]
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1

    init_aws_clients()
    init_db("ingestion-rollout-validation")
    try:
        pending = apply_migrations(dry_run=True)
        failures.extend(f"pending migration: {name}" for name in pending)
        failures.extend(database_failures())
        failures.extend(opensearch_failures())
        failures.extend(generation_coverage_failures())
    except (
        BotoCoreError,
        ClientError,
        OpenSearchException,
        SQLAlchemyError,
        RuntimeError,
    ) as exc:
        failures.append(str(exc))
    finally:
        close_db("ingestion-rollout-validation")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("PASS: controlled ingestion is ready for a test-document rollout.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
