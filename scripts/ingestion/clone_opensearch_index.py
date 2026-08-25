"""Create a non-destructive exact-content clone for ranking-only experiments."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

from collections.abc import Iterator

from opensearchpy import helpers

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings  # noqa: E402
from scripts.ingestion.load_policy_sections_to_opensearch import _client  # noqa: E402


def _validate_targets(source: str, destination: str) -> None:
    if not source.strip() or not destination.strip():
        raise ValueError("Source and destination index names are required.")
    if source == destination:
        raise ValueError("The destination index must be separate from the source index.")


def _source_index_body(client: Any, *, source: str) -> dict[str, Any]:
    """Preserve the source mapping so cloned documents parse identically."""
    response = client.indices.get_mapping(index=source)
    source_mapping = response.get(source, {}).get("mappings")
    if not isinstance(source_mapping, dict) or not source_mapping:
        raise RuntimeError(f"Source index mapping is unavailable: {source}")
    return {
        "settings": {"index": {"knn": True}},
        "mappings": source_mapping,
    }


def _iter_source_documents(
    client: Any,
    *,
    source: str,
    page_size: int = 500,
) -> Iterator[dict[str, Any]]:
    """Yield every source document using OpenSearch Serverless pagination."""
    search_after: list[Any] | None = None
    while True:
        body: dict[str, Any] = {
            "size": page_size,
            "query": {"match_all": {}},
            "sort": [{"id": {"order": "asc"}}],
        }
        if search_after is not None:
            body["search_after"] = search_after
        response = client.search(index=source, body=body)
        hits = list(response.get("hits", {}).get("hits", []))
        if not hits:
            return
        for hit in hits:
            yield hit
        final_sort = hits[-1].get("sort")
        if not isinstance(final_sort, list) or not final_sort:
            raise RuntimeError("Source search response did not include a pagination sort value.")
        search_after = final_sort


def _wait_for_count(
    client: Any,
    *,
    index: str,
    expected: int,
    timeout_seconds: float,
) -> int:
    deadline = time.monotonic() + timeout_seconds
    while True:
        actual = int(client.count(index=index)["count"])
        if actual == expected:
            return actual
        if actual > expected or time.monotonic() >= deadline:
            return actual
        time.sleep(2)


def _index_digest(client: Any, *, index: str) -> str:
    digest = hashlib.sha256()
    for hit in _iter_source_documents(client, source=index):
        canonical = json.dumps(
            hit["_source"],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        digest.update(canonical.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def verify_clone(client: Any, *, source: str, destination: str) -> dict[str, int | str]:
    """Verify equal counts and a deterministic digest of every stored document."""
    _validate_targets(source, destination)
    for name in (source, destination):
        if not client.indices.exists(index=name):
            raise ValueError(f"Index does not exist: {name}")
    source_count = int(client.count(index=source)["count"])
    destination_count = int(client.count(index=destination)["count"])
    if source_count != destination_count:
        raise RuntimeError(
            "Index clone count verification failed: "
            f"source={source_count}, destination={destination_count}."
        )
    source_digest = _index_digest(client, index=source)
    destination_digest = _index_digest(client, index=destination)
    if source_digest != destination_digest:
        raise RuntimeError(
            "Index clone content verification failed: source and destination digests differ."
        )
    return {
        "source": source,
        "destination": destination,
        "source_count": source_count,
        "destination_count": destination_count,
        "content_sha256": source_digest,
    }


def clone_index(
    client: Any,
    *,
    source: str,
    destination: str,
    allow_empty_destination: bool = False,
    verification_timeout_seconds: float = 180,
) -> dict[str, int | str]:
    """Copy logical IDs and stored documents; never overwrite indexed content."""
    _validate_targets(source, destination)
    if not client.indices.exists(index=source):
        raise ValueError(f"Source index does not exist: {source}")
    if client.indices.exists(index=destination):
        destination_count = int(client.count(index=destination)["count"])
        if not allow_empty_destination or destination_count != 0:
            raise ValueError(
                f"Destination index already exists: {destination}. Choose a new versioned name."
            )
    else:
        client.indices.create(
            index=destination,
            body=_source_index_body(client, source=source),
        )

    actions = (
        {
            "_op_type": "index",
            "_index": destination,
            "_source": hit["_source"],
        }
        for hit in _iter_source_documents(client, source=source)
    )
    copied, errors = helpers.bulk(
        client,
        actions,
        raise_on_error=False,
        request_timeout=120,
    )
    source_count = int(client.count(index=source)["count"])
    if errors:
        first = errors[0].get("index", {}) if isinstance(errors[0], dict) else {}
        detail = first.get("error", {}) if isinstance(first, dict) else {}
        raise RuntimeError(
            "Index clone bulk write failed: "
            f"errors={len(errors)}, type={detail.get('type', 'unknown')}, "
            f"reason={detail.get('reason', 'unknown')}."
        )
    destination_count = _wait_for_count(
        client,
        index=destination,
        expected=source_count,
        timeout_seconds=verification_timeout_seconds,
    )
    if copied != source_count or destination_count != source_count:
        raise RuntimeError(
            "Index clone verification failed: "
            f"source={source_count}, copied={copied}, destination={destination_count}, errors={len(errors)}."
        )
    return verify_clone(client, source=source, destination=destination)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="", help="Defaults to OPENSEARCH_INDEX.")
    parser.add_argument("--destination", required=True)
    parser.add_argument(
        "--resume-empty-destination",
        action="store_true",
        help="Reuse an existing destination only when its searchable document count is zero.",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Compare counts and full source-content digests without writing documents.",
    )
    parser.add_argument("--load-ssm", action="store_true")
    args = parser.parse_args()
    if args.load_ssm:
        settings.load_ssm_config()
    client = _client()
    source = args.source or settings.OPENSEARCH_INDEX
    if args.verify_only:
        result = verify_clone(client, source=source, destination=args.destination)
    else:
        result = clone_index(
            client,
            source=source,
            destination=args.destination,
            allow_empty_destination=args.resume_empty_destination,
        )
    print(
        "Verified exact index clone: "
        f"{result['source']} -> {result['destination']} "
        f"({result['source_count']} documents, sha256={result['content_sha256']})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
