"""Capture one bounded retrieval-only run for stateless source-linked cases.

This runner deliberately disables every generative retrieval stage. It permits
only the configured Bedrock embedding model plus read-only OpenSearch searches,
and writes a local replay artifact. It never writes to AWS services or caches.

It cannot reconstruct application session history. A case with stored prior
turns must therefore use an application-pipeline capture; this runner refuses
it before loading configuration or creating any external client.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PACK = ROOT / "tests" / "fixtures" / "held_out_source_linked_pack.json"
MAX_CASES = 24
MAX_EMBEDDING_CALLS = 240


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_pack(path: Path, source_root: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    pack = json.loads(raw)
    cases = pack.get("cases")
    if (
        pack.get("schema_version") != 1
        or pack.get("status") != "approved_and_frozen"
        or not isinstance(cases, list)
        or len(cases) != MAX_CASES
    ):
        raise ValueError("expected the approved and frozen 24-case source-linked pack")
    identifiers = [case.get("id") for case in cases if isinstance(case, dict)]
    if len(identifiers) != MAX_CASES or any(not isinstance(value, str) or not value.strip() for value in identifiers):
        raise ValueError("every case must have a nonblank string id")
    if len(set(identifiers)) != MAX_CASES:
        raise ValueError("case ids must be unique")
    for entry in pack.get("source_extractions") or []:
        source = source_root / str(entry.get("extraction_file") or "")
        if not source.is_file() or _sha256(source) != entry.get("extraction_sha256"):
            raise ValueError(f"missing or drifted source extraction: {source}")
    return pack, hashlib.sha256(raw).hexdigest()


def _require_runtime_context_capture(pack: dict[str, Any]) -> None:
    """Reject a retrieval-only capture that would discard stored user turns."""
    contextual_case_ids = [
        str(case.get("id") or "<missing-id>")
        for case in pack.get("cases") or []
        if isinstance(case, dict) and case.get("conversation")
    ]
    if contextual_case_ids:
        raise ValueError(
            "retrieval-only capture cannot execute cases with stored conversation "
            "turns; use an application-pipeline capture: " + ", ".join(contextual_case_ids)
        )


class _EmbeddingOnlyRuntime:
    def __init__(self, inner: Any, model_id: str) -> None:
        self._inner = inner
        self._model_id = model_id
        self.calls = 0

    def invoke_model(self, **kwargs: Any) -> Any:
        if kwargs.get("modelId") != self._model_id:
            raise RuntimeError("capture permits only the configured embedding model")
        self.calls += 1
        if self.calls > MAX_EMBEDDING_CALLS:
            raise RuntimeError("embedding call ceiling exceeded")
        return self._inner.invoke_model(**kwargs)

    def converse(self, **_kwargs: Any) -> Any:
        raise RuntimeError("generation calls are forbidden in retrieval-only capture")


def _required_sections(case: dict[str, Any]) -> list[str]:
    required = [str(value) for value in (case.get("expected") or {}).get("required_sections") or []]
    source_country = str((case.get("source") or {}).get("country") or "GLOBAL").upper()
    return [value if ":" in value else f"{source_country}:{value}" for value in required]


def _write_new(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=True, separators=(",", ":"))
        handle.write("\n")


def _preload_source_lookup(runtime: dict[str, Any], replay: Any, source_root: Path):
    """Load the staged immutable extraction bundle before any live reads."""
    paths = sorted(source_root.glob("outputs/chunk-comparison-full/current/*/*/*.sections.jsonl"))
    directory = source_root / "tmp/askvera-global-sponsoring/International_Sponsoring_Directory.directory.jsonl"
    if directory.is_file():
        paths.append(directory)
    if not paths:
        raise ValueError("source bundle contains no extraction files")
    rows: dict[str, dict[str, Any]] = {}
    by_section: dict[tuple[str, str, str], dict[str, Any] | None] = {}

    def section_key(row: dict[str, Any]) -> tuple[str, str, str]:
        country = str(row.get("country") or "").upper()
        if country == "UK":
            country = "GB"
        return country, str(row.get("language") or "").lower(), str(row.get("section_id") or "")

    for path in paths:
        for row in replay.load_documents(runtime, path, **replay._document_kind(path)):
            identifier = str(row["id"])
            existing = rows.get(identifier)
            if existing is not None and existing != row:
                raise ValueError(f"conflicting source row id: {identifier}")
            rows[identifier] = row
            key = section_key(row)
            previous = by_section.get(key)
            by_section[key] = row if previous is None or previous == row else None

    def lookup(document: dict[str, Any]) -> dict[str, Any] | None:
        exact = rows.get(str(document.get("id") or ""))
        return exact if exact is not None else by_section.get(section_key(document))

    return lookup, {"files": len(paths), "rows": len(rows)}


def _preflight_source_bundle(source_root: Path) -> dict[str, int]:
    """Prove all staged extraction files are readable before any live request."""
    paths = sorted(source_root.glob("outputs/chunk-comparison-full/current/*/*/*.sections.jsonl"))
    directory = source_root / "tmp/askvera-global-sponsoring/International_Sponsoring_Directory.directory.jsonl"
    if directory.is_file():
        paths.append(directory)
    if not paths:
        raise ValueError("source bundle contains no extraction files")
    return {"files": len(paths), "bytes": sum(len(path.read_bytes()) for path in paths)}


def _active_index_generation_rows(opensearch_sections: Any, settings: Any) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Return generation rows only when every active publication slot is unique."""
    composite: dict[str, Any] = {
        "size": 500,
        "sources": [
            {"access_scope": {"terms": {"field": "access_scope.keyword"}}},
            {"country": {"terms": {"field": "country"}}},
            {"language": {"terms": {"field": "language"}}},
            {"document_type": {"terms": {"field": "document_type"}}},
            {"ingestion_id": {"terms": {"field": "ingestion_id.keyword"}}},
        ],
    }
    groups: dict[tuple[str, str, str, str], set[str]] = {}
    after: dict[str, Any] | None = None
    while True:
        page = dict(composite)
        if after:
            page["after"] = after
        response = opensearch_sections._client().search(
            index=settings.OPENSEARCH_INDEX,
            body={
                "size": 0,
                "query": {"term": {"status": "active"}},
                "aggs": {"slots": {"composite": page}},
            },
        )
        aggregation = response.get("aggregations", {}).get("slots", {})
        buckets = aggregation.get("buckets", [])
        for bucket in buckets:
            key = bucket.get("key", {})
            slot = (
                str(key.get("access_scope") or ""),
                str(key.get("country") or ""),
                str(key.get("language") or ""),
                str(key.get("document_type") or ""),
            )
            groups.setdefault(slot, set()).add(str(key.get("ingestion_id") or ""))
        after = aggregation.get("after_key")
        if not buckets or not after:
            break

    ambiguous = [
        {"slot": list(slot), "generation_count": len(generations)}
        for slot, generations in sorted(groups.items())
        if len(generations) != 1 or "" in generations
    ]
    summary = {
        "status": "unambiguous" if not ambiguous else "ambiguous",
        "active_slots": len(groups),
        "ambiguous_slots": len(ambiguous),
        "ambiguous_sample": ambiguous[:20],
    }
    rows = [
        {
            "access_scope": slot[0],
            "country": slot[1],
            "language": slot[2],
            "document_type": slot[3],
            "active_ingestion_id": next(iter(generations)),
        }
        for slot, generations in sorted(groups.items())
        if len(generations) == 1 and "" not in generations
    ]
    return rows, summary


def _audit_active_index_generations(profile: str) -> dict[str, Any]:
    """Summarize active generation IDs by the publication-pointer dimensions."""
    os.environ["AWS_PROFILE"] = profile
    os.environ.setdefault("AWS_REGION", "us-east-1")
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from config import settings

    settings.load_ssm_config()
    if settings.RETRIEVAL_PROVIDER != "opensearch_section":
        raise RuntimeError("audit requires RETRIEVAL_PROVIDER=opensearch_section")
    if not settings.OPENSEARCH_ENDPOINT or not settings.OPENSEARCH_INDEX:
        raise RuntimeError("OpenSearch endpoint and index must be configured")

    from app.retrieval import opensearch_sections

    _rows, summary = _active_index_generation_rows(opensearch_sections, settings)
    return summary


def _capture(
    pack: dict[str, Any],
    pack_hash: str,
    output: Path,
    profile: str,
    source_root: Path,
) -> dict[str, Any]:
    _require_runtime_context_capture(pack)
    os.environ["AWS_PROFILE"] = profile
    os.environ.setdefault("AWS_REGION", "us-east-1")
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from config import settings

    settings.load_ssm_config()
    if settings.RETRIEVAL_PROVIDER != "opensearch_section":
        raise RuntimeError("capture requires RETRIEVAL_PROVIDER=opensearch_section")
    if not settings.OPENSEARCH_ENDPOINT or not settings.OPENSEARCH_INDEX:
        raise RuntimeError("OpenSearch endpoint and index must be configured")

    # Fail closed against every non-embedding model path and every external
    # write path used by retrieval helpers.
    settings.BEDROCK_QUERY_PLANNER_ENABLED = False
    settings.BEDROCK_EVIDENCE_SELECTOR_ENABLED = False
    settings.OPENSEARCH_EVIDENCE_SELECTOR_ENABLED = False
    settings.OPENSEARCH_LIVE_RERANK_ENABLED = False
    settings.EMBEDDING_SHARED_CACHE_ENABLED = False
    settings.ENABLE_CLOUDWATCH_METRICS = False

    source_bundle_preflight = _preflight_source_bundle(source_root)

    from services import knowledge_generations
    from services.aws_clients import get_aws_clients
    from app.retrieval import opensearch_sections

    generation_rows, generation_audit = _active_index_generation_rows(opensearch_sections, settings)
    if generation_audit["status"] != "unambiguous":
        raise RuntimeError("active index generations are ambiguous")
    # The local workstation cannot reach the production publication-pointer
    # database. The index itself has exactly one active generation per pointer
    # slot, so this isolated runner uses those exact rows instead of guessing.
    knowledge_generations._active_generation_rows = lambda **_kwargs: list(generation_rows)

    clients = get_aws_clients()
    embedding_only = _EmbeddingOnlyRuntime(clients.bedrock_runtime, settings.BEDROCK_EMBED_MODEL_ID)
    clients.bedrock_runtime = embedding_only

    # Planner-off retrieval opens both policy and global scopes. Non-English
    # global translation is generative, so retain the original query instead.
    opensearch_sections.OpenSearchSectionProvider._global_search_query = (
        lambda _self, message, _language, _correlation_id: message
    )
    provider = opensearch_sections.OpenSearchSectionProvider(enable_bedrock_rerank=False)

    raw_cases: list[dict[str, Any]] = []
    for position, case in enumerate(pack["cases"], start=1):
        token = opensearch_sections.enable_rank_list_capture()
        try:
            result = provider.retrieve(
                str(case["question"]),
                str(case["country"]),
                str(case["language"]),
                str(case["role"]),
                f"v2-read-only-capture-{position:02d}",
            )
        finally:
            opensearch_sections.disable_rank_list_capture(token)
        metadata = dict(result.metadata or {})
        if "retrieval_rank_lists" not in metadata:
            raise RuntimeError(f"case {case['id']} did not produce rank-list capture")
        kinds = {str(search.get("kind") or "") for search in metadata["retrieval_rank_lists"].get("searches", [])}
        if not kinds & {"text", "global_text"} or not kinds & {"vector", "global_vector"}:
            raise RuntimeError(f"case {case['id']} did not capture both text and vector retrieval")
        raw_cases.append({"case": case, "metadata": metadata})

    if embedding_only.calls < MAX_CASES:
        raise RuntimeError("capture did not perform one embedding call per frozen case")

    raw_output = output.with_name(f"{output.name}.raw.json")
    _write_new(
        raw_output,
        {
            "schema": "askvera-retrieval-rank-lists/1",
            "pack_sha256": pack_hash,
            "embedding_calls": embedding_only.calls,
            "generation_calls": 0,
            "cases": raw_cases,
        },
    )

    # Resolve identifiers from the source bundle that was fully preloaded and
    # validated before the first live request.
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
    if missing_ids:
        active_ids = {row["active_ingestion_id"] for row in generation_rows}
        for offset in range(0, len(missing_ids), 500):
            chunk = missing_ids[offset : offset + 500]
            response = opensearch_sections._client().search(
                index=settings.OPENSEARCH_INDEX,
                body={
                    "size": len(chunk),
                    "query": {"ids": {"values": chunk}},
                    "_source": {"excludes": ["embedding"]},
                },
            )
            for hit in response.get("hits", {}).get("hits", []):
                source = dict(hit.get("_source") or {})
                identifier = str(hit.get("_id") or source.get("id") or "")
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
            raise RuntimeError("active-index source resolution was incomplete")

    def lookup(document: dict[str, Any]) -> dict[str, Any] | None:
        return local_lookup(document) or index_sources.get(str(document.get("id") or ""))

    converted = []
    for item in raw_cases:
        case = item["case"]
        converted.append(
            replay.capture_case_from_rank_lists(
                item["metadata"],
                case_id=str(case["id"]),
                question=str(case["question"]),
                country=str(case["country"]),
                language=str(case["language"]),
                required_sections=_required_sections(case),
                source_lookup=lookup,
            )
        )

    unresolved = sum(case["source_text"]["identifiers_only"] for case in converted)
    if unresolved:
        raise RuntimeError(f"capture left {unresolved} source rows unresolved")
    artifact = {
        "schema": replay.CAPTURE_SCHEMA,
        "approximate": False,
        "status": "complete",
        "provenance": {
            "pack_sha256": pack_hash,
            "pack_id": pack.get("pack_id"),
            "source_root": str(source_root),
            "aws_account": "615592621509",
            "region": settings.AWS_REGION,
            "index": settings.OPENSEARCH_INDEX,
            "embedding_model": settings.BEDROCK_EMBED_MODEL_ID,
            "embedding_calls": embedding_only.calls,
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
            "source_bundle_bytes_preflight": source_bundle_preflight["bytes"],
            "source_rows_resolved_from_active_index": len(index_sources),
            "raw_rank_lists_sha256": _sha256(raw_output),
            "notes": [
                "Each frozen case was queried exactly once.",
                "Raw text and vector hit ranks/scores came from the configured active OpenSearch index.",
                "Passage text was resolved from the staged local extraction bundle; rows absent from that bundle were read by exact ID from the same active index and content-hash verified.",
                "This capture does not measure generated-answer quality.",
            ],
        },
        "source_resolution": {
            "unresolved_identifier_rows": unresolved,
            "complete": unresolved == 0,
        },
        "cases": converted,
    }
    _write_new(output, artifact)
    return {
        "status": "captured",
        "output": str(output),
        "sha256": _sha256(output),
        "cases": len(converted),
        "embedding_calls": embedding_only.calls,
        "generation_calls": 0,
        "unresolved_identifier_rows": unresolved,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile", default="askvera-baseline")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--audit-generations-only", action="store_true")
    args = parser.parse_args()
    raw_output = args.output.with_name(f"{args.output.name}.raw.json")
    if args.output.exists() or raw_output.exists():
        print(json.dumps({"status": "refused", "reason": "output or raw checkpoint already exists"}))
        return 2
    try:
        pack, pack_hash = _load_pack(args.pack, args.source_root)
        _require_runtime_context_capture(pack)
        if args.validate_only:
            print(json.dumps({"status": "valid", "cases": len(pack["cases"]), "pack_sha256": pack_hash}))
            return 0
        if args.audit_generations_only:
            print(json.dumps(_audit_active_index_generations(args.profile), sort_keys=True))
            return 0
        result = _capture(pack, pack_hash, args.output, args.profile, args.source_root)
    except Exception as exc:  # noqa: BLE001 - one-shot runner reports and stops
        print(json.dumps({"status": "failed", "error": type(exc).__name__, "detail": str(exc)}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
