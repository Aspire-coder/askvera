"""Build an isolated vNext candidate index from the active current corpus.

The default mode is a read-only plan. Execution requires both ``--execute`` and
``--confirm-build-vnext-candidate``. The script never deletes or overwrites an
index and refuses to target the current or configured vNext index.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import asdict, is_dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import unquote, urlparse

import boto3
from botocore.config import Config
from opensearchpy import helpers
from opensearchpy.exceptions import NotFoundError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings  # noqa: E402
from scripts.audit_opensearch_index_parity import (  # noqa: E402
    INVENTORY_FIELDS,
    SOURCE_IDENTITY_FIELDS,
    _aggregation_paths,
    _document_inventory,
)
from scripts.ingestion.extract_policy_sections import extract_sections  # noqa: E402
from scripts.ingestion.extract_global_office_directory import (  # noqa: E402
    extract_directory as extract_office_directory,
)
from scripts.ingestion.extract_global_sponsoring_directory import (  # noqa: E402
    extract_directory as extract_sponsoring_directory,
)
from scripts.ingestion.load_policy_sections_to_opensearch import (  # noqa: E402
    _actions,
    _client,
    _index_body,
)


def _s3_location(source_uri: str) -> tuple[str, str, str]:
    parsed = urlparse(source_uri)
    key = unquote(parsed.path.lstrip("/"))
    filename = Path(key).name
    if parsed.scheme != "s3" or not parsed.netloc or not key or not filename:
        raise ValueError(f"Unsupported source URI: {source_uri}")
    if not filename.lower().endswith(".pdf"):
        raise ValueError(f"vNext rebuild currently requires a PDF: {source_uri}")
    return parsed.netloc, key, filename


def _source_plan(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for row in rows:
        identity = tuple(str(row.get(field) or "") for field in SOURCE_IDENTITY_FIELDS)
        grouped.setdefault(identity, []).append(row)

    plan: list[dict[str, str]] = []
    for identity, variants in sorted(grouped.items()):
        metadata = {
            field: sorted({str(row.get(field) or "") for row in variants})
            for field in ("logical_document_id", "document_version", "effective_date")
        }
        conflicting = {field: values for field, values in metadata.items() if len(values) > 1}
        if conflicting:
            raise ValueError(
                f"Active source has conflicting metadata: {identity[0]}: {conflicting}"
            )
        source = dict(zip(SOURCE_IDENTITY_FIELDS, identity, strict=True))
        _s3_location(source["source_uri"])
        plan.append(
            {
                **source,
                **{field: values[0] if values else "" for field, values in metadata.items()},
            }
        )
    return plan


def _section_documents(sections: list[Any]) -> list[dict[str, Any]]:
    """Convert extractor dataclasses to the loader's JSON-compatible shape."""
    documents: list[dict[str, Any]] = []
    for section in sections:
        if isinstance(section, dict):
            documents.append(section)
        elif is_dataclass(section) and not isinstance(section, type):
            documents.append(asdict(section))
        else:
            raise TypeError(
                f"Unsupported extracted section type: {type(section).__name__}"
            )
    return documents


def _source_documents(
    local_path: Path,
    source: dict[str, str],
    *,
    chunk_profile: str,
) -> list[dict[str, Any]]:
    """Use the source-type extractor that produced the live document shape."""
    if source["document_type"] == "office_directory":
        if "sponsoring" in local_path.name.casefold():
            records = extract_sponsoring_directory(local_path)
        else:
            office_records, staff_records = extract_office_directory(local_path)
            records = [*office_records, *staff_records]
        return [
            {
                **record.to_row(),
                "chunk_profile": chunk_profile,
                "document_version": source["document_version"],
                "effective_date": source["effective_date"],
            }
            for record in records
        ]

    return _section_documents(
        extract_sections(
            local_path,
            country=source["country"],
            language=source["language"],
            document_version=source["document_version"],
            effective_date=source["effective_date"],
            status="active",
            chunk_profile=chunk_profile,
        )
    )


def _validate_candidate_index(candidate_index: str) -> None:
    if not candidate_index:
        raise ValueError("--candidate-index is required.")
    if candidate_index in {settings.OPENSEARCH_INDEX, settings.OPENSEARCH_VNEXT_INDEX}:
        raise ValueError(
            "Candidate index must differ from both current and configured vNext indexes."
        )
    if "vnext" not in candidate_index or "candidate" not in candidate_index:
        raise ValueError("Candidate index name must contain both 'vnext' and 'candidate'.")


def _load_current_plan(client: Any) -> list[dict[str, str]]:
    paths = _aggregation_paths(client, settings.OPENSEARCH_INDEX)
    rows = _document_inventory(
        client,
        settings.OPENSEARCH_INDEX,
        identity_fields=INVENTORY_FIELDS,
        aggregation_paths=paths,
    )
    return _source_plan(rows)


def _build_candidate(
    *,
    client: Any,
    s3: Any,
    candidate_index: str,
    plan: list[dict[str, str]],
    replace_empty_candidate: bool = False,
    resume_candidate: bool = False,
    start_source: int = 1,
    end_source: int | None = None,
    chunk_profile: str = "vnext",
) -> dict[str, Any]:
    create_index = True
    if client.indices.exists(index=candidate_index):
        if resume_candidate:
            create_index = False
        elif not replace_empty_candidate:
            raise ValueError(
                "Candidate index already exists and will not be overwritten: "
                f"{candidate_index}"
            )
        else:
            existing_count = int(
                client.count(index=candidate_index).get("count", 0)
            )
            if existing_count:
                raise ValueError(
                    "Candidate cleanup refused because the existing index contains "
                    f"{existing_count} records: {candidate_index}"
                )
            client.indices.delete(index=candidate_index)
    if create_index:
        client.indices.create(index=candidate_index, body=_index_body())
    indexed_chunks = 0
    completed_sources = 0
    with TemporaryDirectory(prefix="askvera-vnext-candidate-") as directory:
        temporary_root = Path(directory)
        for sequence, source in enumerate(plan, start=1):
            if sequence < start_source or (
                end_source is not None and sequence > end_source
            ):
                continue
            bucket, key, filename = _s3_location(source["source_uri"])
            local_path = temporary_root / filename
            s3.download_file(bucket, key, str(local_path))
            sections = _source_documents(
                local_path,
                source,
                chunk_profile=chunk_profile,
            )
            ingestion_id = uuid.uuid4().hex
            source_prefix = source["source_uri"].rsplit("/", 1)[0]
            actions = _actions(
                sections,
                index=candidate_index,
                source_uri_prefix=source_prefix,
                status="active",
                ingestion_id=ingestion_id,
                document_type=source["document_type"],
                access_scope=source["access_scope"],
            )
            for action in actions:
                action["_source"]["logical_document_id"] = source[
                    "logical_document_id"
                ]
                action["_source"].setdefault("metadata", {})[
                    "logical_document_id"
                ] = source["logical_document_id"]
            success, errors = helpers.bulk(client, actions, raise_on_error=False)
            if errors:
                raise RuntimeError(
                    f"OpenSearch rejected {len(errors)} chunks for "
                    f"{source['source_uri']}: "
                    f"{json.dumps(errors[:2], ensure_ascii=False, default=str)}"
                )
            indexed_chunks += int(success)
            completed_sources += 1
    refresh_supported = True
    try:
        client.indices.refresh(index=candidate_index)
    except NotFoundError:
        # OpenSearch Serverless may reject explicit refresh; indexed writes
        # become searchable through the service's normal consistency cycle.
        refresh_supported = False
    return {
        "candidate_index": candidate_index,
        "completed_sources": completed_sources,
        "indexed_chunks": indexed_chunks,
        "explicit_refresh_supported": refresh_supported,
        "chunk_profile": chunk_profile,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-index", required=True)
    parser.add_argument("--load-ssm", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-build-vnext-candidate", action="store_true")
    parser.add_argument(
        "--replace-empty-candidate",
        action="store_true",
        help="Delete and recreate the candidate only when its total record count is zero.",
    )
    parser.add_argument(
        "--resume-candidate",
        action="store_true",
        help="Use an existing isolated candidate without deleting it.",
    )
    parser.add_argument("--start-source", type=int, default=1)
    parser.add_argument("--end-source", type=int)
    parser.add_argument(
        "--chunk-profile",
        choices=("vnext", "vnext_r4"),
        default="vnext",
        help="Experimental extraction profile used for the isolated candidate.",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.load_ssm:
        settings.load_ssm_config()
    _validate_candidate_index(args.candidate_index)
    if args.start_source < 1:
        raise ValueError("--start-source must be at least 1.")
    if args.end_source is not None and args.end_source < args.start_source:
        raise ValueError("--end-source cannot be lower than --start-source.")
    client = _client()
    plan = _load_current_plan(client)
    result: dict[str, Any] = {
        "mode": "execute" if args.execute else "plan",
        "current_index": settings.OPENSEARCH_INDEX,
        "configured_vnext_index": settings.OPENSEARCH_VNEXT_INDEX,
        "candidate_index": args.candidate_index,
        "chunk_profile": args.chunk_profile,
        "source_count": len(plan),
        "sources": plan,
    }
    if args.execute:
        if not args.confirm_build_vnext_candidate:
            raise ValueError(
                "Execution requires --confirm-build-vnext-candidate."
            )
        session = boto3.Session(region_name=settings.AWS_REGION)
        s3 = session.client(
            "s3",
            config=Config(
                retries={"total_max_attempts": settings.AWS_MAX_ATTEMPTS, "mode": "adaptive"},
                connect_timeout=5,
                read_timeout=60,
            ),
        )
        result["build"] = _build_candidate(
            client=client,
            s3=s3,
            candidate_index=args.candidate_index,
            plan=plan,
            replace_empty_candidate=args.replace_empty_candidate,
            resume_candidate=args.resume_candidate,
            start_source=args.start_source,
            end_source=args.end_source,
            chunk_profile=args.chunk_profile,
        )
    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print(f"output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
