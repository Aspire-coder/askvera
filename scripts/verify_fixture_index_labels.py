"""Verify held-out ground-truth labels against active OpenSearch documents.

The audit is read-only and metadata-only. It does not retrieve chunk content,
invoke a model, update an index, or touch answer/session caches.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_paraphrase_profile_evaluation import (  # noqa: E402
    candidate_is_relevant,
    normalize_fixture,
)


def _metadata_query(case: dict[str, Any]) -> dict[str, Any]:
    from app.retrieval.opensearch_sections import (
        GLOBAL_DIRECTORY_DOCUMENT_TYPES,
        _generation_filters,
        _scope_filter,
    )

    scope = "global" if case.get("scope") == "global_directory" else "locale"
    filters: list[dict[str, Any]] = [
        _scope_filter(str(case.get("country") or ""), str(case.get("language") or "en"), scope),
        {"term": {"status": "active"}},
        *_generation_filters(
            str(case.get("country") or ""),
            str(case.get("language") or "en"),
            scope,
        ),
    ]
    if scope == "global":
        filters.append({"terms": {"document_type": list(GLOBAL_DIRECTORY_DOCUMENT_TYPES)}})
    return {
        "size": 5000,
        "_source": [
            "id",
            "source_file",
            "section_id",
            "document_type",
            "access_scope",
            "country",
            "language",
            "metadata.record_country",
        ],
        "query": {"bool": {"filter": filters}},
    }


def _candidate_from_hit(hit: dict[str, Any]) -> dict[str, Any]:
    source = dict(hit.get("_source") or {})
    metadata = dict(source.get("metadata") or {})
    return {
        "id": str(source.get("id") or hit.get("_id") or ""),
        "source_file": str(source.get("source_file") or ""),
        "section_id": str(source.get("section_id") or ""),
        "document_type": str(source.get("document_type") or ""),
        "access_scope": str(source.get("access_scope") or ""),
        "country": str(source.get("country") or ""),
        "language": str(source.get("language") or ""),
        "record_country": str(metadata.get("record_country") or ""),
    }


def matching_rows(rows: list[dict[str, Any]], case: dict[str, Any]) -> list[dict[str, Any]]:
    """Return metadata rows that satisfy the evaluator's ground truth."""
    return [row for row in rows if candidate_is_relevant(row, case)]


def _normalized_tokens(value: str) -> set[str]:
    """Return useful alphanumeric tokens for content-free metadata diagnosis."""
    return {
        token
        for token in re.findall(r"[a-z0-9]+", str(value or "").casefold())
        if len(token) > 1
    }


def _section_prefixes(relevant_sections: list[str]) -> tuple[set[str], set[str]]:
    """Return exact numeric section stems and broader chapter prefixes."""
    stems: set[str] = set()
    chapters: set[str] = set()
    for section in relevant_sections:
        match = re.match(r"^\s*(\d+(?:\.\d+)*)", str(section or ""))
        if not match:
            continue
        stem = match.group(1)
        stems.add(stem)
        chapters.add(stem.split(".", 1)[0])
    return stems, chapters


def nearby_rows(
    rows: list[dict[str, Any]],
    case: dict[str, Any],
    *,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Return nearby metadata rows for a missing label without exposing content.

    Exact section stems are preferred. If none exist, the result falls back to
    the same numeric chapter. Global-directory cases use the configured label
    and target-country tokens across section and record-country metadata.
    """
    relevant_sections = [str(value) for value in case.get("relevant_sections") or []]
    scope = str(case.get("scope") or "")
    if scope == "global_directory":
        target_tokens = _normalized_tokens(str(case.get("target_country") or ""))
        for section in relevant_sections:
            target_tokens.update(
                _normalized_tokens(section)
                - {"sponsoring", "directory", "international", "global"}
            )
        if not target_tokens:
            return []
        ranked: list[tuple[int, dict[str, Any]]] = []
        for row in rows:
            section_tokens = _normalized_tokens(str(row.get("section_id") or ""))
            country_tokens = _normalized_tokens(str(row.get("record_country") or ""))
            score = (3 * len(target_tokens & country_tokens)) + len(target_tokens & section_tokens)
            if score:
                ranked.append((score, row))
        ranked.sort(
            key=lambda item: (
                -item[0],
                str(item[1].get("record_country") or ""),
                str(item[1].get("section_id") or ""),
            )
        )
        return [row for _score, row in ranked[:limit]]

    stems, chapters = _section_prefixes(relevant_sections)
    exact_stem_rows = [
        row
        for row in rows
        if any(
            re.match(rf"^{re.escape(stem)}(?:$|[-_:/(])", str(row.get("section_id") or ""))
            for stem in stems
        )
    ]
    candidates = exact_stem_rows
    if not candidates:
        candidates = [
            row
            for row in rows
            if any(
                re.match(rf"^{re.escape(chapter)}(?:$|[.\-_:/(])", str(row.get("section_id") or ""))
                for chapter in chapters
            )
        ]
    return sorted(candidates, key=lambda row: str(row.get("section_id") or ""))[:limit]


def audit_index(
    *,
    index_name: str,
    cases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    from app.retrieval.opensearch_sections import _client

    client = _client()
    cache: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    results: list[dict[str, Any]] = []
    for case in cases:
        if case.get("expected_behavior") == "abstain" or case.get("scope") == "out_of_scope":
            results.append({"id": case["id"], "status": "not_applicable", "matches": []})
            continue
        cache_key = (
            str(case.get("scope") or ""),
            str(case.get("country") or ""),
            str(case.get("language") or ""),
        )
        if cache_key not in cache:
            response = client.search(index=index_name, body=_metadata_query(case))
            hits = list((response.get("hits") or {}).get("hits") or [])
            cache[cache_key] = [_candidate_from_hit(hit) for hit in hits]
        matches = matching_rows(cache[cache_key], case)
        has_ground_truth = bool(case.get("relevant_sections") or case.get("target_country"))
        status = "present" if matches else ("missing" if has_ground_truth else "no_ground_truth")
        nearby = nearby_rows(cache[cache_key], case) if status == "missing" else []
        results.append(
            {
                "id": case["id"],
                "status": status,
                "matches": matches,
                "configured_relevant_sections": list(case.get("relevant_sections") or []),
                "target_country": str(case.get("target_country") or ""),
                "nearby_rows": nearby,
            }
        )
    return results


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = ["# Held-out Index Label Audit", ""]
    for profile in ("current", "candidate"):
        rows = payload[profile]
        counts = Counter(row["status"] for row in rows)
        lines.extend(
            [
                f"## {profile.title()}",
                "",
                f"Index: `{payload['indexes'][profile]}`",
                "",
                "| Status | Cases |",
                "|---|---:|",
            ]
        )
        for status, count in sorted(counts.items()):
            lines.append(f"| {status} | {count} |")
        lines.extend(["", "### Missing or unlabeled cases", ""])
        flagged = [row for row in rows if row["status"] in {"missing", "no_ground_truth"}]
        if not flagged:
            lines.append("None.")
        else:
            for row in flagged:
                lines.append(
                    f"- `{row['id']}`: {row['status']}; labels: "
                    f"{', '.join(row.get('configured_relevant_sections') or []) or 'none'}"
                )
                for nearby in row.get("nearby_rows") or []:
                    lines.append(
                        "  - nearby metadata: "
                        f"section `{nearby.get('section_id') or 'none'}`, "
                        f"record country `{nearby.get('record_country') or 'none'}`, "
                        f"source `{nearby.get('source_file') or 'none'}`"
                    )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--load-ssm", action="store_true")
    parser.add_argument("--current-index", default="")
    parser.add_argument("--candidate-index", default="")
    args = parser.parse_args()

    raw_fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    fixture, _changes = normalize_fixture(raw_fixture)
    from config import settings

    if args.load_ssm:
        settings.load_ssm_config()
    indexes = {
        "current": args.current_index or settings.OPENSEARCH_INDEX,
        "candidate": args.candidate_index or settings.OPENSEARCH_VNEXT_INDEX,
    }
    payload = {
        "indexes": indexes,
        "current": audit_index(index_name=indexes["current"], cases=fixture["cases"]),
        "candidate": audit_index(index_name=indexes["candidate"], cases=fixture["cases"]),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "index-label-audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "index-label-audit.md").write_text(
        _render_markdown(payload),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
