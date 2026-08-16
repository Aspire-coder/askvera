"""Register published S3 ingestion generations in the admin document registry.

Bulk policy publication predates the portal upload workflow, so it can populate
S3 and OpenSearch without creating the RDS rows used by the Knowledge page.
This script makes that historical publication visible without changing content.
It is dry-run by default; pass --apply to write the registry rows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

from sqlalchemy import text

from config import settings
from services.aws_clients import get_aws_clients
from services.db import get_engine
from services.knowledge_generations import build_logical_document_id

COUNTRY_ALIASES = {"UK": "GB"}


def _objects(bucket: str, prefix: str) -> list[dict[str, Any]]:
    client = get_aws_clients().s3
    result: list[dict[str, Any]] = []
    token = None
    while True:
        params = {"Bucket": bucket, "Prefix": prefix}
        if token:
            params["ContinuationToken"] = token
        page = client.list_objects_v2(**params)
        result.extend(item for item in page.get("Contents", []) if str(item["Key"]).endswith(".sections.jsonl"))
        if not page.get("IsTruncated"):
            return result
        token = page.get("NextContinuationToken")


def _read_sections(bucket: str, key: str) -> tuple[dict[str, Any], int, str]:
    body = get_aws_clients().s3.get_object(Bucket=bucket, Key=key)["Body"]
    first: dict[str, Any] | None = None
    count = 0
    digest = hashlib.sha256()
    for raw_line in body.iter_lines():
        line = bytes(raw_line)
        if not line.strip():
            continue
        digest.update(line)
        section = json.loads(line)
        if first is None:
            first = section
        count += 1
    if first is None:
        raise ValueError(f"Published section file is empty: s3://{bucket}/{key}")
    return first, count, digest.hexdigest()


def _record(item: dict[str, Any], *, apply: bool) -> dict[str, Any]:
    bucket = settings.S3_BUCKET
    key = str(item["Key"])
    first, section_count, content_hash = _read_sections(bucket, key)
    source_country = str(first.get("country") or "").upper()
    country = COUNTRY_ALIASES.get(source_country, source_country)
    language = str(first.get("language") or "").lower()
    filename = str(first.get("source_file") or PurePosixPath(key).name.replace(".sections.jsonl", ""))
    access_scope = "global" if country in {"GLOBAL", ""} else "country"
    document_type = "policy"
    source_uri = f"s3://{bucket}/{key}"
    document_id = f"bulk-{hashlib.sha256(source_uri.encode()).hexdigest()}"
    logical_document_id = build_logical_document_id(
        logical_document_id="",
        country=country or "GLOBAL",
        language=language or "en",
        document_type=document_type,
        access_scope=access_scope,
        source_file=filename,
    )
    version = str(first.get("document_version") or "")
    effective_date = str(first.get("effective_date") or "")
    created_at = item.get("LastModified") or datetime.now().astimezone()
    record = {
        "job_id": document_id,
        "filename": filename,
        "country": country,
        "language": language,
        "document_type": document_type,
        "access_scope": access_scope,
        "document_version": version,
        "progress": 100,
        "section_count": section_count,
        "source_uri": source_uri,
        "content_hash": content_hash,
        "logical_document_id": logical_document_id,
        "created_at": created_at,
    }
    if apply:
        with get_engine().begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO ingestion_jobs (
                        job_id, filename, country, language, document_type,
                        access_scope, document_version, status, progress,
                        section_count, source_uri, content_hash, completed_at,
                        logical_document_id, created_at, updated_at
                    ) VALUES (
                        :job_id, :filename, :country, :language, :document_type,
                        :access_scope, :document_version, 'ready', :progress,
                        :section_count, :source_uri, :content_hash, :created_at,
                        :logical_document_id, :created_at, :created_at
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
                        completed_at = EXCLUDED.completed_at,
                        logical_document_id = EXCLUDED.logical_document_id,
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
                        section_count, content_hash, logical_document_id,
                        status, created_at, updated_at
                    ) VALUES (
                        :job_id, :filename, :source_uri, :country, :language,
                        :document_type, :access_scope, :document_version,
                        :section_count, :content_hash, :logical_document_id,
                        'active', :created_at, :created_at
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
                        logical_document_id = EXCLUDED.logical_document_id,
                        status = 'active',
                        updated_at = now()
                    """
                ),
                record,
            )
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--country", help="Only backfill a country code, such as IT")
    parser.add_argument("--apply", action="store_true", help="Write registry rows; otherwise print a dry run")
    args = parser.parse_args()
    settings.load_ssm_config(settings.SSM_PARAMETER_PATH)
    items = _objects(settings.S3_BUCKET, "ingestion/")
    if args.country:
        country_marker = f"/{args.country.upper()}/"
        items = [item for item in items if country_marker in str(item["Key"])]
    records = [_record(item, apply=args.apply) for item in items]
    for record in records:
        print(json.dumps({key: value.isoformat() if isinstance(value, datetime) else value for key, value in record.items()}, default=str))
    print(f"{'Registered' if args.apply else 'Would register'} {len(records)} published document(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
