"""Audit active document parity between current and vNext OpenSearch indexes."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.retrieval.opensearch_sections import _client  # noqa: E402
from config import settings  # noqa: E402


SOURCE_IDENTITY_FIELDS = (
    "source_uri",
    "country",
    "language",
    "document_type",
    "access_scope",
)
METADATA_FIELDS = (
    "logical_document_id",
    "document_version",
    "effective_date",
)
INVENTORY_FIELDS = SOURCE_IDENTITY_FIELDS + METADATA_FIELDS


def _aggregation_paths(client: Any, index_name: str) -> dict[str, str]:
    response = client.indices.get_mapping(index=index_name)
    index_mapping = response.get(index_name)
    if index_mapping is None and response:
        index_mapping = next(iter(response.values()))
    properties = ((index_mapping or {}).get("mappings") or {}).get("properties") or {}
    paths: dict[str, str] = {}
    for field in (*INVENTORY_FIELDS, "ingestion_id"):
        mapping = properties.get(field) or {}
        if mapping.get("type") in {"keyword", "date"}:
            paths[field] = field
        elif ((mapping.get("fields") or {}).get("keyword") or {}).get("type") == "keyword":
            paths[field] = f"{field}.keyword"
    return paths


def _document_inventory(
    client: Any,
    index_name: str,
    *,
    identity_fields: tuple[str, ...] = INVENTORY_FIELDS,
    aggregation_paths: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Return one aggregation row per active document generation."""
    aggregation_paths = aggregation_paths or _aggregation_paths(client, index_name)
    aggregate_fields = [
        field
        for field in (*identity_fields, "ingestion_id")
        if field in aggregation_paths
    ]
    rows: list[dict[str, Any]] = []
    after: dict[str, Any] | None = None
    while True:
        composite: dict[str, Any] = {
            "size": 500,
            "sources": [
                {
                    field: {
                        "terms": {
                            "field": aggregation_paths[field],
                            "missing_bucket": True,
                        }
                    }
                }
                for field in aggregate_fields
            ],
        }
        if after:
            composite["after"] = after
        response = client.search(
            index=index_name,
            body={
                "size": 0,
                "query": {"term": {"status": "active"}},
                "aggs": {"documents": {"composite": composite}},
            },
        )
        aggregation = response.get("aggregations", {}).get("documents", {})
        for bucket in aggregation.get("buckets", []):
            key = dict(bucket.get("key") or {})
            rows.append(
                {
                    **{field: str(key.get(field) or "") for field in identity_fields},
                    "ingestion_id": str(key.get("ingestion_id") or ""),
                    "chunk_count": int(bucket.get("doc_count") or 0),
                }
            )
        after = aggregation.get("after_key")
        if not after:
            break
    return rows


def _identity(row: dict[str, Any], fields: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(str(row.get(field) or "") for field in fields)


def _metadata_value(field: str, value: Any) -> str:
    rendered = str(value or "")
    if field != "effective_date" or not rendered:
        return rendered
    if rendered.isdigit():
        return datetime.fromtimestamp(int(rendered) / 1000, tz=UTC).date().isoformat()
    return rendered[:10]


def compare_inventories(
    current_rows: list[dict[str, Any]],
    vnext_rows: list[dict[str, Any]],
    *,
    source_identity_fields: tuple[str, ...] = SOURCE_IDENTITY_FIELDS,
    metadata_fields: tuple[str, ...] = METADATA_FIELDS,
    current_available_fields: set[str] | None = None,
    vnext_available_fields: set[str] | None = None,
) -> dict[str, Any]:
    current_available_fields = current_available_fields or set(INVENTORY_FIELDS)
    vnext_available_fields = vnext_available_fields or set(INVENTORY_FIELDS)

    def grouped(rows: list[dict[str, Any]]) -> dict[tuple[str, ...], list[dict[str, Any]]]:
        result: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for row in rows:
            result.setdefault(_identity(row, source_identity_fields), []).append(row)
        return result

    current = grouped(current_rows)
    vnext = grouped(vnext_rows)
    current_only = sorted(set(current) - set(vnext))
    vnext_only = sorted(set(vnext) - set(current))
    shared = sorted(set(current) & set(vnext))

    generation_id_differences = [
        {
            "document": dict(zip(source_identity_fields, identity, strict=True)),
            "current_ingestion_ids": sorted(
                {str(row.get("ingestion_id") or "") for row in current[identity]}
            ),
            "vnext_ingestion_ids": sorted(
                {str(row.get("ingestion_id") or "") for row in vnext[identity]}
            ),
        }
        for identity in shared
        if {str(row.get("ingestion_id") or "") for row in current[identity]}
        != {str(row.get("ingestion_id") or "") for row in vnext[identity]}
    ]

    comparable_metadata_fields = tuple(
        field
        for field in metadata_fields
        if field in current_available_fields and field in vnext_available_fields
    )
    metadata_mismatches: list[dict[str, Any]] = []
    for identity in shared:
        differences: dict[str, Any] = {}
        for field in comparable_metadata_fields:
            current_values = sorted(
                {_metadata_value(field, row.get(field)) for row in current[identity]}
            )
            vnext_values = sorted(
                {_metadata_value(field, row.get(field)) for row in vnext[identity]}
            )
            if current_values != vnext_values:
                differences[field] = {
                    "current": current_values,
                    "vnext": vnext_values,
                }
        if differences:
            metadata_mismatches.append(
                {
                    "document": dict(
                        zip(source_identity_fields, identity, strict=True)
                    ),
                    "differences": differences,
                }
            )

    chunk_count_differences = [
        {
            "document": dict(zip(source_identity_fields, identity, strict=True)),
            "current_chunk_count": sum(
                int(row.get("chunk_count") or 0) for row in current[identity]
            ),
            "vnext_chunk_count": sum(
                int(row.get("chunk_count") or 0) for row in vnext[identity]
            ),
        }
        for identity in shared
        if sum(int(row.get("chunk_count") or 0) for row in current[identity])
        != sum(int(row.get("chunk_count") or 0) for row in vnext[identity])
    ]
    current_unavailable_metadata = sorted(
        set(metadata_fields) - current_available_fields
    )
    vnext_unavailable_metadata = sorted(set(metadata_fields) - vnext_available_fields)
    source_set_parity = not current_only and not vnext_only
    metadata_parity = (
        not current_unavailable_metadata
        and not vnext_unavailable_metadata
        and not metadata_mismatches
    )
    return {
        "current_active_document_generations": len(current_rows),
        "vnext_active_document_generations": len(vnext_rows),
        "compared_source_identity_fields": list(source_identity_fields),
        "compared_metadata_fields": list(comparable_metadata_fields),
        "shared_documents": len(shared),
        "source_set_parity": source_set_parity,
        "document_set_parity": source_set_parity,
        "metadata_parity": metadata_parity,
        "evaluation_ready": source_set_parity and metadata_parity,
        "current_unavailable_metadata_fields": current_unavailable_metadata,
        "vnext_unavailable_metadata_fields": vnext_unavailable_metadata,
        "current_only_documents": [
            dict(zip(source_identity_fields, identity, strict=True))
            for identity in current_only
        ],
        "vnext_only_documents": [
            dict(zip(source_identity_fields, identity, strict=True))
            for identity in vnext_only
        ],
        "metadata_mismatches": metadata_mismatches,
        "generation_id_differences": generation_id_differences,
        "chunk_count_differences": chunk_count_differences,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "interaction_quality" / "index-parity.json",
    )
    parser.add_argument("--load-ssm", action="store_true")
    parser.add_argument("--current-index", default="")
    parser.add_argument("--vnext-index", default="")
    args = parser.parse_args()
    if args.load_ssm:
        settings.load_ssm_config()
    current_index = args.current_index or settings.OPENSEARCH_INDEX
    vnext_index = args.vnext_index or settings.OPENSEARCH_VNEXT_INDEX
    if not current_index or not vnext_index:
        raise RuntimeError("Both OPENSEARCH_INDEX and OPENSEARCH_VNEXT_INDEX are required.")
    client = _client()
    current_paths = _aggregation_paths(client, current_index)
    vnext_paths = _aggregation_paths(client, vnext_index)
    missing_source_fields = sorted(
        set(SOURCE_IDENTITY_FIELDS) - set(current_paths),
    ) + sorted(set(SOURCE_IDENTITY_FIELDS) - set(vnext_paths))
    if missing_source_fields:
        raise RuntimeError(
            "Both indexes must expose all source identity fields as keywords: "
            + ", ".join(sorted(set(missing_source_fields)))
        )
    result = compare_inventories(
        _document_inventory(
            client,
            current_index,
            identity_fields=INVENTORY_FIELDS,
            aggregation_paths=current_paths,
        ),
        _document_inventory(
            client,
            vnext_index,
            identity_fields=INVENTORY_FIELDS,
            aggregation_paths=vnext_paths,
        ),
        current_available_fields=set(current_paths),
        vnext_available_fields=set(vnext_paths),
    )
    result["current_unavailable_inventory_fields"] = sorted(
        set(INVENTORY_FIELDS) - set(current_paths)
    )
    result["vnext_unavailable_inventory_fields"] = sorted(
        set(INVENTORY_FIELDS) - set(vnext_paths)
    )
    result["current_index"] = current_index
    result["vnext_index"] = vnext_index
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"output: {args.output}")
    return 0 if result["evaluation_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
