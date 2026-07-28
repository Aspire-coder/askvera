"""Compare current and vNext JSONL chunk packages before OpenSearch loading."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import mean, median
from typing import Any


def _load(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}") from exc
    if not rows:
        raise ValueError(f"No chunks found in {path}")
    return rows


def _percentile(values: list[int], percentile: float) -> int:
    ordered = sorted(values)
    index = round((len(ordered) - 1) * percentile)
    return ordered[index]


def summarize(path: Path) -> dict[str, Any]:
    rows = _load(path)
    lengths = [len(str(row.get("content", ""))) for row in rows]
    profiles = Counter(
        str(row.get("chunk_profile") or row.get("metadata", {}).get("chunk_profile") or "current")
        for row in rows
    )
    chunk_types = Counter(str(row.get("chunk_type") or "section") for row in rows)
    parent_sections = {
        str(row.get("parent_section_id") or row.get("section_id") or "")
        for row in rows
    }
    return {
        "path": str(path),
        "chunks": len(rows),
        "parent_sections": len(parent_sections),
        "profiles": dict(sorted(profiles.items())),
        "characters": {
            "minimum": min(lengths),
            "median": round(median(lengths)),
            "mean": round(mean(lengths)),
            "p95": _percentile(lengths, 0.95),
            "maximum": max(lengths),
        },
        "chunk_types": dict(sorted(chunk_types.items())),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", required=True, type=Path)
    parser.add_argument("--vnext", required=True, type=Path)
    parser.add_argument("--json-output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = {
        "current": summarize(args.current),
        "vnext": summarize(args.vnext),
    }
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    print(rendered)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
