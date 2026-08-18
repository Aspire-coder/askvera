"""Clone the live retrieval content into an isolated rank-only candidate.

The default mode is read-only. Execution requires both ``--execute`` and
``--confirm-clone-current``. The script never updates, deletes, or overwrites
an index and refuses to target the configured current or vNext index.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

from opensearchpy import helpers
from opensearchpy.exceptions import NotFoundError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.retrieval.opensearch_sections import _client  # noqa: E402
from config import settings  # noqa: E402


def _validate_candidate_index(candidate_index: str) -> None:
    if not candidate_index:
        raise ValueError("--candidate-index is required.")
    protected = {settings.OPENSEARCH_INDEX, settings.OPENSEARCH_VNEXT_INDEX}
    if candidate_index in protected:
        raise ValueError(
            "Candidate index must differ from both current and configured vNext indexes."
        )
    if "vnext" not in candidate_index or "candidate" not in candidate_index:
        raise ValueError("Candidate index name must contain both 'vnext' and 'candidate'.")


def _source_index_body(client: Any, source_index: str) -> dict[str, Any]:
    mapping_response = client.indices.get_mapping(index=source_index)
    settings_response = client.indices.get_settings(index=source_index)
    mapping = deepcopy(mapping_response[source_index]["mappings"])
    source_settings = settings_response[source_index]["settings"]["index"]
    body: dict[str, Any] = {"mappings": mapping}
    if str(source_settings.get("knn", "false")).casefold() == "true":
        body["settings"] = {"index": {"knn": True}}
    return body


def _unique_keyword_count(client: Any, index_name: str, field: str) -> int:
    count = 0
    after: dict[str, Any] | None = None
    while True:
        composite: dict[str, Any] = {
            "size": 1000,
            "sources": [{"value": {"terms": {"field": field}}}],
        }
        if after:
            composite["after"] = after
        response = client.search(
            index=index_name,
            body={
                "size": 0,
                "aggs": {"unique_values": {"composite": composite}},
            },
        )
        aggregation = response.get("aggregations", {}).get("unique_values", {})
        buckets = aggregation.get("buckets", [])
        count += len(buckets)
        after = aggregation.get("after_key")
        if not after:
            return count


def _iter_documents(client: Any, index_name: str) -> Iterable[dict[str, Any]]:
    search_after: list[Any] | None = None
    while True:
        body: dict[str, Any] = {
            "size": 250,
            "track_total_hits": False,
            "query": {"match_all": {}},
            "sort": [{"id": {"order": "asc"}}],
        }
        if search_after is not None:
            body["search_after"] = search_after
        response = client.search(index=index_name, body=body)
        hits = response.get("hits", {}).get("hits", [])
        if not hits:
            return
        yield from hits
        next_search_after = hits[-1].get("sort")
        if not next_search_after or next_search_after == search_after:
            raise RuntimeError("OpenSearch search_after pagination did not advance.")
        search_after = next_search_after


def _clone_actions(
    client: Any, source_index: str, candidate_index: str
) -> Iterable[dict[str, Any]]:
    for hit in _iter_documents(client, source_index):
        yield {
            "_op_type": "create",
            "_index": candidate_index,
            "_source": hit["_source"],
        }


def _document_digest(hit: dict[str, Any]) -> str:
    rendered = json.dumps(
        hit["_source"],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _index_fingerprint(client: Any, index_name: str) -> dict[str, Any]:
    document_digests = sorted(
        _document_digest(hit)
        for hit in _iter_documents(client, index_name)
    )
    fingerprint = hashlib.sha256(
        "\n".join(document_digests).encode("ascii")
    ).hexdigest()
    return {"document_count": len(document_digests), "sha256": fingerprint}


def _wait_for_count(
    client: Any,
    index_name: str,
    expected_count: int,
    *,
    attempts: int = 24,
    delay_seconds: float = 5.0,
) -> int:
    observed = -1
    for attempt in range(max(1, attempts)):
        observed = int(client.count(index=index_name).get("count", 0))
        if observed == expected_count:
            return observed
        if attempt + 1 < attempts:
            time.sleep(max(0.0, delay_seconds))
    return observed


def _clone_current_index(
    *,
    client: Any,
    source_index: str,
    candidate_index: str,
    verify_content: bool = True,
) -> dict[str, Any]:
    if client.indices.exists(index=candidate_index):
        raise ValueError(
            "Candidate index already exists and will not be overwritten: "
            f"{candidate_index}"
        )
    source_count = int(client.count(index=source_index).get("count", 0))
    unique_id_count = _unique_keyword_count(client, source_index, "id")
    if unique_id_count != source_count:
        raise RuntimeError(
            "Stable clone pagination requires one unique id per source document: "
            f"source={source_count}, unique_ids={unique_id_count}"
        )
    client.indices.create(
        index=candidate_index,
        body=_source_index_body(client, source_index),
    )
    indexed_count, errors = helpers.bulk(
        client,
        _clone_actions(client, source_index, candidate_index),
        chunk_size=200,
        request_timeout=120,
        raise_on_error=False,
        raise_on_exception=False,
    )
    if errors:
        raise RuntimeError(
            f"OpenSearch rejected {len(errors)} cloned documents: "
            f"{json.dumps(errors[:2], ensure_ascii=False, default=str)}"
        )
    refresh_supported = True
    try:
        client.indices.refresh(index=candidate_index)
    except NotFoundError:
        refresh_supported = False
    candidate_count = _wait_for_count(client, candidate_index, source_count)
    if indexed_count != source_count or candidate_count != source_count:
        raise RuntimeError(
            "Candidate count parity failed: "
            f"source={source_count}, indexed={indexed_count}, candidate={candidate_count}"
        )

    result: dict[str, Any] = {
        "source_index": source_index,
        "candidate_index": candidate_index,
        "source_count": source_count,
        "unique_id_count": unique_id_count,
        "indexed_count": int(indexed_count),
        "candidate_count": candidate_count,
        "explicit_refresh_supported": refresh_supported,
        "count_parity": True,
    }
    if verify_content:
        source_fingerprint = _index_fingerprint(client, source_index)
        candidate_fingerprint = _index_fingerprint(client, candidate_index)
        content_parity = source_fingerprint == candidate_fingerprint
        result.update(
            {
                "source_fingerprint": source_fingerprint,
                "candidate_fingerprint": candidate_fingerprint,
                "content_parity": content_parity,
            }
        )
        if not content_parity:
            raise RuntimeError("Candidate content fingerprint does not match production.")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-index", required=True)
    parser.add_argument("--load-ssm", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-clone-current", action="store_true")
    parser.add_argument("--skip-content-verification", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.load_ssm:
        settings.load_ssm_config()
    _validate_candidate_index(args.candidate_index)
    client = _client()
    if client.indices.exists(index=args.candidate_index):
        raise ValueError(
            "Candidate index already exists and will not be overwritten: "
            f"{args.candidate_index}"
        )
    result: dict[str, Any] = {
        "mode": "execute" if args.execute else "plan",
        "source_index": settings.OPENSEARCH_INDEX,
        "configured_vnext_index": settings.OPENSEARCH_VNEXT_INDEX,
        "candidate_index": args.candidate_index,
        "source_count": int(
            client.count(index=settings.OPENSEARCH_INDEX).get("count", 0)
        ),
        "clone_contract": {
            "reextract_documents": False,
            "regenerate_embeddings": False,
            "preserve_source_document_ids": True,
            "preserve_opensearch_internal_ids": False,
            "preserve_source_fields": True,
            "overwrite_existing_index": False,
            "change_production_configuration": False,
        },
    }
    if args.execute:
        if not args.confirm_clone_current:
            raise ValueError("Execution requires --confirm-clone-current.")
        result["clone"] = _clone_current_index(
            client=client,
            source_index=settings.OPENSEARCH_INDEX,
            candidate_index=args.candidate_index,
            verify_content=not args.skip_content_verification,
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
