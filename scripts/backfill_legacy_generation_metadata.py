"""Preview or repair missing generation metadata on legacy active records."""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from opensearchpy import helpers
from opensearchpy.exceptions import OpenSearchException

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings  # noqa: E402
from scripts.ingestion.load_policy_sections_to_opensearch import _client  # noqa: E402
from services.aws_clients import init_aws_clients  # noqa: E402
from services.knowledge_generations import build_logical_document_id  # noqa: E402
from utils.logging import configure_logging  # noqa: E402


@dataclass(frozen=True)
class LegacyMetadataRepair:
    document_id: str
    country: str
    language: str
    source_file: str
    document_type: str
    access_scope: str
    ingestion_id: str
    logical_document_id: str
    update: dict[str, str]


def deterministic_legacy_ingestion_id(logical_document_id: str) -> str:
    """Return a stable synthetic generation ID for an unversioned legacy source."""
    digest = hashlib.sha256(
        f"askvera-legacy-generation:{logical_document_id}".encode("utf-8")
    ).hexdigest()
    return f"legacy-{digest[:32]}"


def _inferred_access_scope(country: str) -> str:
    return "global" if country.upper() == "GLOBAL" else "country"


def legacy_metadata_repairs(
    records: Iterable[dict[str, Any]],
) -> list[LegacyMetadataRepair]:
    """Build repairs only when every source has one unambiguous generation."""
    grouped: dict[
        tuple[str, str, str, str],
        list[tuple[str, dict[str, Any]]],
    ] = defaultdict(list)

    for record in records:
        source = record.get("_source", record)
        document_id = str(record.get("_id") or "")
        identity = (
            str(source.get("country") or "").upper(),
            str(source.get("language") or "").lower(),
            str(source.get("source_file") or ""),
            str(source.get("document_type") or "").lower(),
        )
        if not document_id or not all(identity):
            raise ValueError(
                "An active OpenSearch record is missing its ID or source identity."
            )
        grouped[identity].append((document_id, source))

    repairs: list[LegacyMetadataRepair] = []
    for identity, source_records in sorted(grouped.items()):
        country, language, source_file, document_type = identity
        scopes = {
            str(source.get("access_scope") or "").lower()
            for _document_id, source in source_records
            if source.get("access_scope")
        }
        if len(scopes) > 1:
            raise ValueError(
                f"Multiple access scopes exist for {country}/{language}/{source_file}."
            )
        access_scope = next(iter(scopes), _inferred_access_scope(country))
        if access_scope not in {"country", "global"}:
            raise ValueError(
                f"Unsupported access scope for {country}/{language}/{source_file}: "
                f"{access_scope}"
            )

        logical_document_id = build_logical_document_id(
            logical_document_id="",
            country=country,
            language=language,
            document_type=document_type,
            access_scope=access_scope,
            source_file=source_file,
        )
        ingestion_ids = {
            str(source.get("ingestion_id") or "")
            for _document_id, source in source_records
            if source.get("ingestion_id")
        }
        if len(ingestion_ids) > 1:
            raise ValueError(
                "Multiple active generations exist for "
                f"{country}/{language}/{source_file}: "
                f"{', '.join(sorted(ingestion_ids))}"
            )
        ingestion_id = next(
            iter(ingestion_ids),
            deterministic_legacy_ingestion_id(logical_document_id),
        )

        for document_id, source in source_records:
            if source.get("access_scope") and source.get("ingestion_id"):
                continue
            current_logical_id = str(source.get("logical_document_id") or "")
            if current_logical_id and current_logical_id != logical_document_id:
                raise ValueError(
                    f"Conflicting logical document ID on OpenSearch record {document_id}."
                )
            update: dict[str, str] = {}
            if not source.get("access_scope"):
                update["access_scope"] = access_scope
            if not source.get("ingestion_id"):
                update["ingestion_id"] = ingestion_id
            if not current_logical_id:
                update["logical_document_id"] = logical_document_id
            if update:
                repairs.append(
                    LegacyMetadataRepair(
                        document_id=document_id,
                        country=country,
                        language=language,
                        source_file=source_file,
                        document_type=document_type,
                        access_scope=access_scope,
                        ingestion_id=ingestion_id,
                        logical_document_id=logical_document_id,
                        update=update,
                    )
                )
    return repairs


def load_active_records(
    *,
    client: Any | None = None,
    page_size: int = 1000,
) -> Iterable[dict[str, Any]]:
    """Page through active metadata using Serverless-compatible search_after."""
    search_client = client or _client()
    search_after: list[Any] | None = None
    while True:
        body: dict[str, Any] = {
            "size": page_size,
            "track_total_hits": False,
            "_source": [
                "country",
                "language",
                "source_file",
                "document_type",
                "access_scope",
                "ingestion_id",
                "logical_document_id",
            ],
            "sort": [{"_id": "asc"}],
            "query": {"term": {"status": "active"}},
        }
        if search_after is not None:
            body["search_after"] = search_after
        response = search_client.search(index=settings.OPENSEARCH_INDEX, body=body)
        hits = response.get("hits", {}).get("hits", [])
        if not hits:
            return
        yield from hits
        if len(hits) < page_size:
            return
        next_search_after = hits[-1].get("sort")
        if not isinstance(next_search_after, list) or not next_search_after:
            raise RuntimeError(
                "OpenSearch did not return a search_after token for a full page."
            )
        if next_search_after == search_after:
            raise RuntimeError("OpenSearch pagination token did not advance.")
        search_after = next_search_after


def apply_repairs(
    repairs: Iterable[LegacyMetadataRepair],
    *,
    client: Any | None = None,
) -> tuple[int, list[Any]]:
    repair_list = list(repairs)
    if not repair_list:
        return 0, []
    search_client = client or _client()
    return helpers.bulk(
        search_client,
        (
            {
                "_op_type": "update",
                "_index": settings.OPENSEARCH_INDEX,
                "_id": repair.document_id,
                "doc": repair.update,
            }
            for repair in repair_list
        ),
        raise_on_error=False,
        raise_on_exception=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the reviewed repairs. The default is a read-only dry run.",
    )
    parser.add_argument("--load-ssm", action="store_true")
    args = parser.parse_args()

    configure_logging()
    if args.load_ssm:
        settings.load_ssm_config()
    init_aws_clients()
    try:
        repairs = legacy_metadata_repairs(load_active_records())
        grouped: dict[tuple[str, str, str], int] = defaultdict(int)
        for repair in repairs:
            grouped[
                (repair.country, repair.language, repair.source_file)
            ] += 1
        print(f"Legacy records requiring metadata repair: {len(repairs)}")
        for identity, count in sorted(grouped.items()):
            country, language, source_file = identity
            print(f"- {country}/{language}/{source_file}: {count}")
        if not args.apply:
            print("Dry run only. Re-run with --apply after reviewing every source.")
            return 0

        updated, errors = apply_repairs(repairs)
        print(f"Updated legacy records: {updated}")
        print(f"Update errors: {len(errors)}")
        if errors or updated != len(repairs):
            raise RuntimeError(
                f"Expected {len(repairs)} updates, completed {updated} with "
                f"{len(errors)} errors."
            )
        print("PASS: legacy generation metadata repair was applied.")
        return 0
    except (OpenSearchException, RuntimeError, TypeError, ValueError) as exc:
        print(f"Legacy metadata repair failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
