"""Preview or apply retention cleanup for knowledge-ingestion artifacts."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError
from opensearchpy import helpers
from sqlalchemy import bindparam, text
from sqlalchemy.exc import SQLAlchemyError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings  # noqa: E402
from scripts.ingestion.load_policy_sections_to_opensearch import _client  # noqa: E402
from services.aws_clients import get_aws_clients, init_aws_clients  # noqa: E402
from services.db import close_db, get_engine, init_db  # noqa: E402
from utils.logging import configure_logging  # noqa: E402
from utils.opensearch_fields import exact_terms_query  # noqa: E402


def quarantine_candidates(now: datetime) -> list[dict[str, Any]]:
    """List expired quarantine objects without deleting them."""
    cutoff = now - timedelta(days=settings.ADMIN_INGESTION_QUARANTINE_RETENTION_DAYS)
    bucket = settings.KNOWLEDGE_UPLOAD_BUCKET
    prefix = settings.ADMIN_INGESTION_QUARANTINE_PREFIX.strip("/") + "/"
    if not bucket:
        return []
    paginator = get_aws_clients().s3.get_paginator("list_objects_v2")
    return [
        item
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix)
        for item in page.get("Contents", [])
        if item.get("LastModified") and item["LastModified"] < cutoff
    ]


def retired_generation_candidates(now: datetime) -> list[str]:
    """Return retired ingestion IDs whose rollback window has elapsed."""
    cutoff = now - timedelta(
        days=settings.ADMIN_INGESTION_RETIRED_GENERATION_RETENTION_DAYS
    )
    with get_engine().connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT ingestion_id
                FROM knowledge_document_generations
                WHERE status = 'retired'
                  AND retired_at IS NOT NULL
                  AND retired_at < :cutoff
                ORDER BY retired_at
                """
            ),
            {"cutoff": cutoff},
        ).scalars().all()
    return [str(value) for value in rows]


def apply_cleanup(
    quarantine: list[dict[str, Any]],
    retired_ingestion_ids: list[str],
) -> tuple[int, int]:
    """Delete the selected artifacts and mark retired generations deleted."""
    s3_deleted = 0
    bucket = settings.KNOWLEDGE_UPLOAD_BUCKET
    s3 = get_aws_clients().s3
    for offset in range(0, len(quarantine), 1000):
        batch = quarantine[offset:offset + 1000]
        if not batch:
            continue
        response = s3.delete_objects(
            Bucket=bucket,
            Delete={
                "Objects": [{"Key": str(item["Key"])} for item in batch],
                "Quiet": True,
            },
        )
        if response.get("Errors"):
            raise RuntimeError(
                f"S3 rejected {len(response['Errors'])} quarantine deletions."
            )
        s3_deleted += len(batch)

    search_deleted = 0
    if retired_ingestion_ids:
        client = _client()
        actions = (
            {
                "_op_type": "delete",
                "_index": settings.OPENSEARCH_INDEX,
                "_id": hit["_id"],
            }
            for hit in helpers.scan(
                client,
                index=settings.OPENSEARCH_INDEX,
                query={
                    "_source": False,
                    "query": {
                        **exact_terms_query(
                            "ingestion_id",
                            retired_ingestion_ids,
                        )
                    },
                },
            )
        )
        search_deleted, errors = helpers.bulk(
            client,
            actions,
            raise_on_error=False,
            raise_on_exception=False,
        )
        if errors:
            raise RuntimeError(
                f"OpenSearch rejected {len(errors)} retired-generation deletions."
            )
        statement = text(
            """
            UPDATE knowledge_document_generations
            SET status = 'deleted'
            WHERE ingestion_id IN :ingestion_ids
            """
        ).bindparams(bindparam("ingestion_ids", expanding=True))
        with get_engine().begin() as connection:
            connection.execute(
                statement,
                {"ingestion_ids": retired_ingestion_ids},
            )
    return s3_deleted, int(search_deleted)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the listed deletions. The default is a dry run.",
    )
    parser.add_argument("--load-ssm", action="store_true")
    args = parser.parse_args()

    configure_logging()
    if args.load_ssm:
        settings.load_ssm_config()
    init_aws_clients()
    init_db("knowledge-retention")
    try:
        now = datetime.now(UTC)
        quarantine = quarantine_candidates(now)
        retired = retired_generation_candidates(now)
        print(f"Expired quarantine objects: {len(quarantine)}")
        print(f"Expired retired generations: {len(retired)}")
        if not args.apply:
            print("Dry run only. Re-run with --apply after reviewing the counts.")
            return 0
        s3_deleted, search_deleted = apply_cleanup(quarantine, retired)
        print(f"Deleted quarantine objects: {s3_deleted}")
        print(f"Deleted retired OpenSearch records: {search_deleted}")
        return 0
    except (BotoCoreError, ClientError, SQLAlchemyError, RuntimeError) as exc:
        print(f"Knowledge cleanup failed: {exc}", file=sys.stderr)
        return 1
    finally:
        close_db("knowledge-retention")


if __name__ == "__main__":
    raise SystemExit(main())
