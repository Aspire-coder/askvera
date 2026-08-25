"""Create a non-destructive exact-content clone for ranking-only experiments."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from opensearchpy import helpers

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings  # noqa: E402
from scripts.ingestion.load_policy_sections_to_opensearch import (  # noqa: E402
    _client,
    _index_body,
)


def _validate_targets(source: str, destination: str) -> None:
    if not source.strip() or not destination.strip():
        raise ValueError("Source and destination index names are required.")
    if source == destination:
        raise ValueError("The destination index must be separate from the source index.")


def clone_index(client: Any, *, source: str, destination: str) -> dict[str, int | str]:
    """Copy IDs and stored documents exactly; never overwrite an existing index."""
    _validate_targets(source, destination)
    if not client.indices.exists(index=source):
        raise ValueError(f"Source index does not exist: {source}")
    if client.indices.exists(index=destination):
        raise ValueError(
            f"Destination index already exists: {destination}. Choose a new versioned name."
        )

    client.indices.create(index=destination, body=_index_body())
    actions = (
        {
            "_op_type": "index",
            "_index": destination,
            "_id": hit["_id"],
            "_source": hit["_source"],
        }
        for hit in helpers.scan(
            client,
            index=source,
            query={"query": {"match_all": {}}},
            preserve_order=False,
        )
    )
    copied, errors = helpers.bulk(
        client,
        actions,
        raise_on_error=False,
        request_timeout=120,
    )
    client.indices.refresh(index=destination)
    source_count = int(client.count(index=source)["count"])
    destination_count = int(client.count(index=destination)["count"])
    if errors or copied != source_count or destination_count != source_count:
        raise RuntimeError(
            "Index clone verification failed: "
            f"source={source_count}, copied={copied}, destination={destination_count}, errors={len(errors)}."
        )
    return {
        "source": source,
        "destination": destination,
        "source_count": source_count,
        "destination_count": destination_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="", help="Defaults to OPENSEARCH_INDEX.")
    parser.add_argument("--destination", required=True)
    parser.add_argument("--load-ssm", action="store_true")
    args = parser.parse_args()
    if args.load_ssm:
        settings.load_ssm_config()
    result = clone_index(
        _client(),
        source=args.source or settings.OPENSEARCH_INDEX,
        destination=args.destination,
    )
    print(
        "Verified exact index clone: "
        f"{result['source']} -> {result['destination']} ({result['source_count']} documents)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
