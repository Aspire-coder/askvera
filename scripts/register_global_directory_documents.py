"""Register the legacy global directory PDFs in the Knowledge portal registry.

The international directory PDFs were published before portal ingestion jobs
were introduced. Their live retrieval records therefore exist, but the
Knowledge page has no document rows to display. This idempotent repair creates
the missing registry rows without changing the indexed content.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings
from scripts.ingestion.load_policy_sections_to_opensearch import _client
from services.aws_clients import get_aws_clients
from services.db import get_engine


GLOBAL_DIRECTORY_KEYS = {
    "International-Office-Directory-April-2026.pdf": (
        "approved/Global_en/directories/International-Office-Directory-April-2026.pdf",
        "office_directory",
        "2026-04",
    ),
    "International-Sponsoring-Directory.pdf": (
        "approved/Global_en/directories/International-Sponsoring-Directory.pdf",
        "office_directory",
        "2026-08",
    ),
}


def _source_metadata(filename: str, source_uri: str) -> tuple[str, int]:
    """Return a live ingestion id and indexed chunk count when available."""
    response = _client().search(
        index=settings.OPENSEARCH_INDEX,
        body={
            "size": 0,
            "track_total_hits": True,
            "query": {
                "bool": {
                    "must": [
                        {"term": {"source_uri": source_uri}},
                        {"term": {"status": "active"}},
                    ]
                }
            },
            "aggs": {"ingestion_ids": {"terms": {"field": "ingestion_id", "size": 5}}},
        },
    )
    buckets = response.get("aggregations", {}).get("ingestion_ids", {}).get("buckets", [])
    ingestion_id = str(buckets[0].get("key") or "") if buckets else ""
    total = response.get("hits", {}).get("total", 0)
    count = int(total.get("value", 0) if isinstance(total, dict) else total)
    if not ingestion_id:
        ingestion_id = f"legacy-{hashlib.sha256(source_uri.encode()).hexdigest()[:32]}"
    return ingestion_id, count


def register(*, apply: bool) -> list[dict[str, Any]]:
    s3 = get_aws_clients().s3
    records: list[dict[str, Any]] = []
    for filename, (key, document_type, version) in GLOBAL_DIRECTORY_KEYS.items():
        head = s3.head_object(Bucket=settings.S3_BUCKET, Key=key)
        source_uri = f"s3://{settings.S3_BUCKET}/{key}"
        ingestion_id, section_count = _source_metadata(filename, source_uri)
        last_modified = head.get("LastModified") or datetime.now().astimezone()
        content_hash = hashlib.sha256(f"{source_uri}:{head.get('ETag', '')}".encode()).hexdigest()
        record = {
            "job_id": ingestion_id,
            "filename": filename,
            "country": "GLOBAL",
            "language": "en",
            "document_type": document_type,
            "access_scope": "global",
            "document_version": version,
            "section_count": section_count,
            "source_uri": source_uri,
            "content_hash": content_hash,
            "created_at": last_modified,
        }
        if apply:
            with get_engine().begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO ingestion_jobs (
                            job_id, filename, country, language, document_type,
                            access_scope, document_version, status, progress,
                            section_count, source_uri, content_hash, created_at, updated_at
                        ) VALUES (
                            :job_id, :filename, :country, :language, :document_type,
                            :access_scope, :document_version, 'ready', 100,
                            :section_count, :source_uri, :content_hash, :created_at, :created_at
                        )
                        ON CONFLICT (job_id) DO UPDATE SET
                            filename = EXCLUDED.filename,
                            country = EXCLUDED.country,
                            language = EXCLUDED.language,
                            document_type = EXCLUDED.document_type,
                            access_scope = EXCLUDED.access_scope,
                            document_version = EXCLUDED.document_version,
                            status = 'ready',
                            progress = 100,
                            section_count = EXCLUDED.section_count,
                            source_uri = EXCLUDED.source_uri,
                            content_hash = EXCLUDED.content_hash,
                            updated_at = now()
                        """
                    ),
                    record,
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO knowledge_documents (
                            document_id, filename, source_uri, country, language,
                            document_type, access_scope, document_version,
                            section_count, content_hash, status, created_at, updated_at
                        ) VALUES (
                            :job_id, :filename, :source_uri, :country, :language,
                            :document_type, :access_scope, :document_version,
                            :section_count, :content_hash, 'active', :created_at, :created_at
                        )
                        ON CONFLICT (document_id) DO UPDATE SET
                            filename = EXCLUDED.filename,
                            source_uri = EXCLUDED.source_uri,
                            country = EXCLUDED.country,
                            language = EXCLUDED.language,
                            document_type = EXCLUDED.document_type,
                            access_scope = EXCLUDED.access_scope,
                            document_version = EXCLUDED.document_version,
                            section_count = EXCLUDED.section_count,
                            content_hash = EXCLUDED.content_hash,
                            status = 'active',
                            updated_at = now()
                        """
                    ),
                    record,
                )
        records.append(record)
    return records


def main() -> int:
    settings.load_ssm_config()
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    records = register(apply=args.apply)
    print(json.dumps({"applied": args.apply, "records": records}, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
