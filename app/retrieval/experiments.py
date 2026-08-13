"""Opt-in retrieval experiment helpers kept separate from the live baseline."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Hashable, Iterable, Sequence


def reciprocal_rank_fusion(
    rankings: Sequence[Iterable[Hashable]], *, k: int = 60
) -> dict[Hashable, float]:
    """Fuse ranked candidate IDs without changing either source ranking."""
    denominator = max(1, int(k))
    scores: dict[Hashable, float] = defaultdict(float)
    for ranking in rankings:
        seen: set[Hashable] = set()
        for position, key in enumerate(ranking, start=1):
            if key in seen:
                continue
            seen.add(key)
            scores[key] += 1.0 / (denominator + position)
    return dict(scores)


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


def bounded_neighbor_ids(
    selected_ids: Iterable[str], neighbor_ids: Iterable[str], *, limit: int
) -> list[str]:
    """Return a deterministic, bounded union for optional context expansion."""
    result: list[str] = []
    seen: set[str] = set()
    for value in [*selected_ids, *neighbor_ids]:
        cleaned = str(value).strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
        if len(result) >= max(0, int(limit)):
            break
    return result
