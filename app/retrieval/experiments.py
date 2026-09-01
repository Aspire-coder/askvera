"""Opt-in retrieval experiment helpers kept separate from the live baseline."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Sequence


def diversify_by_parent(
    documents: Sequence[dict[str, Any]], *, max_results: int, max_per_parent: int = 1
) -> list[dict[str, Any]]:
    """Bound repeated chunks from one parent section while preserving rank order."""
    result: list[dict[str, Any]] = []
    counts: dict[str, int] = defaultdict(int)
    limit = max(0, int(max_results))
    per_parent = max(1, int(max_per_parent))
    for document in documents:
        metadata = document.get("metadata") if isinstance(document, dict) else {}
        metadata = metadata if isinstance(metadata, dict) else {}
        parent = str(
            metadata.get("parent_section_id")
            or metadata.get("section_id")
            or document.get("id", "")
        )
        if counts[parent] >= per_parent:
            continue
        result.append(document)
        counts[parent] += 1
        if len(result) >= limit:
            break
    return result
