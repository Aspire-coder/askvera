"""Finalize a checkpointed retrieval capture without repeating model calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evidence_first_v2.capture_read_only_retrieval import (
    MAX_CASES,
    _active_index_generation_rows,
    _load_pack,
    _preload_source_lookup,
    _require_runtime_context_capture,
    _required_sections,
    _sha256,
    _write_new,
)


def _finalize(raw_path: Path, pack_path: Path, source_root: Path, output: Path, profile: str) -> dict[str, Any]:
    pack, pack_hash = _load_pack(pack_path, source_root)
    _require_runtime_context_capture(pack)
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    raw_cases = raw.get("cases")
    if (
        raw.get("schema") != "askvera-retrieval-rank-lists/1"
        or raw.get("pack_sha256") != pack_hash
        or raw.get("generation_calls") != 0
        or int(raw.get("embedding_calls") or 0) < MAX_CASES
        or not isinstance(raw_cases, list)
        or len(raw_cases) != MAX_CASES
    ):
        raise ValueError("raw checkpoint does not match the frozen complete capture")
    expected_ids = [str(case["id"]) for case in pack["cases"]]
    actual_ids = [str(item.get("case", {}).get("id") or "") for item in raw_cases]
    if actual_ids != expected_ids:
        raise ValueError("raw checkpoint case order or identity differs from the frozen pack")

    os.environ["AWS_PROFILE"] = profile
    os.environ.setdefault("AWS_REGION", "us-east-1")
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from config import settings

    settings.load_ssm_config()
    if settings.RETRIEVAL_PROVIDER != "opensearch_section":
        raise RuntimeError("finalization requires RETRIEVAL_PROVIDER=opensearch_section")
    from app.retrieval import opensearch_sections

    generation_rows, generation_audit = _active_index_generation_rows(opensearch_sections, settings)
    if generation_audit["status"] != "unambiguous":
        raise RuntimeError("active index generations are ambiguous")

    from scripts import offline_retrieval_replay as replay

    runtime = replay._import_runtime(ROOT)
    local_lookup, source_bundle = _preload_source_lookup(runtime, replay, source_root)
    captured_documents = {
        document["id"]: document
        for item in raw_cases
        for document in (
            dict(zip(replay._RANK_LIST_DOCUMENT_FIELDS, row))
            for row in item["metadata"]["retrieval_rank_lists"].get("documents", [])
        )
    }
    missing_ids = sorted(identifier for identifier, document in captured_documents.items() if local_lookup(document) is None)
    index_sources: dict[str, dict[str, Any]] = {}
    active_ids = {row["active_ingestion_id"] for row in generation_rows}
    for offset in range(0, len(missing_ids), 500):
        chunk = missing_ids[offset : offset + 500]
        response = opensearch_sections._client().search(
            index=settings.OPENSEARCH_INDEX,
            body={
                "size": len(chunk),
                "query": {"terms": {"id": chunk}},
                "_source": {"excludes": ["embedding"]},
            },
        )
        for hit in response.get("hits", {}).get("hits", []):
            source = dict(hit.get("_source") or {})
            identifier = str(source.get("id") or "")
            content = str(source.get("content") or "")
            if (
                identifier not in chunk
                or source.get("status") != "active"
                or source.get("ingestion_id") not in active_ids
                or not content
                or hashlib.sha256(content.encode("utf-8")).hexdigest() != source.get("content_hash")
            ):
                raise RuntimeError(f"invalid active-index source row: {identifier}")
            source.pop("embedding", None)
            index_sources[identifier] = source
    if set(missing_ids) != set(index_sources):
        unresolved = sorted(set(missing_ids) - set(index_sources))
        raise RuntimeError(f"active-index source resolution missed {len(unresolved)} rows")

    def lookup(document: dict[str, Any]) -> dict[str, Any] | None:
        return local_lookup(document) or index_sources.get(str(document.get("id") or ""))

    converted = [
        replay.capture_case_from_rank_lists(
            item["metadata"],
            case_id=str(item["case"]["id"]),
            question=str(item["case"]["question"]),
            country=str(item["case"]["country"]),
            language=str(item["case"]["language"]),
            required_sections=_required_sections(item["case"]),
            source_lookup=lookup,
        )
        for item in raw_cases
    ]
    unresolved_count = sum(case["source_text"]["identifiers_only"] for case in converted)
    if unresolved_count:
        raise RuntimeError(f"final capture left {unresolved_count} source rows unresolved")

    artifact = {
        "schema": replay.CAPTURE_SCHEMA,
        "approximate": False,
        "status": "complete",
        "provenance": {
            "pack_sha256": pack_hash,
            "pack_id": pack.get("pack_id"),
            "raw_rank_lists_sha256": _sha256(raw_path),
            "source_root": str(source_root),
            "aws_account": "615592621509",
            "region": settings.AWS_REGION,
            "index": settings.OPENSEARCH_INDEX,
            "embedding_model": settings.BEDROCK_EMBED_MODEL_ID,
            "embedding_calls": int(raw["embedding_calls"]),
            "generation_calls": 0,
            "query_planner": "disabled",
            "evidence_selector": "disabled",
            "live_reranker": "disabled",
            "global_translation": "disabled; original query retained",
            "shared_embedding_cache": "disabled; no cache reads or writes",
            "writes_to_aws": 0,
            "generation_pointer_source": "unique active OpenSearch slots",
            "active_generation_slots": generation_audit["active_slots"],
            "source_bundle_files": source_bundle["files"],
            "source_bundle_rows": source_bundle["rows"],
            "source_rows_resolved_from_active_index": len(index_sources),
            "notes": [
                "All rank lists came from the checkpointed 24-case retrieval-only run.",
                "Raw text and vector ranks and scores came from the configured active OpenSearch index.",
                "Rows absent from the staged source bundle were read by exact document id and content-hash verified.",
                "This capture does not measure generated-answer quality.",
            ],
        },
        "source_resolution": {"unresolved_identifier_rows": 0, "complete": True},
        "cases": converted,
    }
    _write_new(output, artifact)
    return {
        "status": "finalized",
        "output": str(output),
        "sha256": _sha256(output),
        "cases": len(converted),
        "embedding_calls": int(raw["embedding_calls"]),
        "generation_calls": 0,
        "source_rows_from_active_index": len(index_sources),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--pack", type=Path, default=ROOT / "tests/fixtures/held_out_source_linked_pack.json")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile", default="askvera-baseline")
    args = parser.parse_args()
    if args.output.exists():
        print(json.dumps({"status": "refused", "reason": "output already exists"}))
        return 2
    try:
        result = _finalize(args.raw, args.pack, args.source_root, args.output, args.profile)
    except Exception as exc:  # noqa: BLE001 - one-shot finalizer reports and stops
        print(json.dumps({"status": "failed", "error": type(exc).__name__, "detail": str(exc)}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
