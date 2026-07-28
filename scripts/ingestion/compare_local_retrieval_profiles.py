"""Compare lexical retrieval stability between current and vNext chunk packages."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate_local_section_search import _load_sections, search_sections  # noqa: E402

SECTION_FAMILY_RE = re.compile(r"^(\d+(?:\.\d+)?)")


def _text(value: Any) -> str:
    if value is None:
        return ""
    rendered = str(value).strip()
    return "" if rendered.lower() == "nan" else rendered


def _section_family(row: dict[str, Any]) -> str:
    value = _text(row.get("parent_section_id") or row.get("section_id"))
    match = SECTION_FAMILY_RE.match(value)
    return match.group(1) if match else value


def _package(root: Path, market: str, language: str) -> Path | None:
    matches = sorted((root / market / language).glob("*.jsonl"))
    return matches[0] if len(matches) == 1 else None


def compare(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    import pandas as pd

    frame = pd.read_excel(args.xlsx, sheet_name=args.sheet, header=args.header_row)
    rows: list[dict[str, Any]] = []
    package_cache: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for _, test in frame.iterrows():
        if _text(test.get("Retrieval expected")).casefold() != "yes":
            continue
        if _text(test.get("Expected scope")).casefold() != "country policy":
            continue
        question = _text(test.get("Question"))
        market = _text(test.get("Market")).upper()
        language = _text(test.get("Language")).lower()
        if not question or not market or not language:
            continue

        current_path = _package(args.current_root, market, language)
        vnext_path = _package(args.vnext_root, market, language)
        if current_path is None or vnext_path is None:
            rows.append(
                {
                    "test_id": _text(test.get("Test ID")),
                    "market": market,
                    "language": language,
                    "question": question,
                    "status": "MISSING_PACKAGE",
                }
            )
            continue

        def sections(profile: str, path: Path) -> list[dict[str, Any]]:
            key = (profile, market, language)
            if key not in package_cache:
                package_cache[key] = _load_sections(path)
            return package_cache[key]

        current = search_sections(question, sections("current", current_path), args.top_k)
        vnext = search_sections(question, sections("vnext", vnext_path), args.top_k)
        current_families = [_section_family(row) for row in current]
        vnext_families = [_section_family(row) for row in vnext]
        shared = set(current_families) & set(vnext_families)
        current_top = current_families[0] if current_families else ""
        vnext_top = vnext_families[0] if vnext_families else ""
        both_have_results = bool(current and vnext)
        both_empty = not current and not vnext
        rows.append(
            {
                "test_id": _text(test.get("Test ID")),
                "market": market,
                "language": language,
                "question": question,
                "status": "COMPARED" if both_have_results else ("BOTH_NO_RESULT" if both_empty else "PROFILE_NO_RESULT"),
                "current_top_family": current_top,
                "vnext_top_family": vnext_top,
                "top_family_match": current_top == vnext_top and bool(current_top),
                "current_top_in_vnext_top5": current_top in vnext_families[:5] if current_top else False,
                "current_top_in_vnext_top10": current_top in vnext_families[:10] if current_top else False,
                "top10_family_overlap": round(len(shared) / max(1, len(set(current_families) | set(vnext_families))), 4),
                "current_top_chars": len(_text(current[0].get("content"))) if current else 0,
                "vnext_top_chars": len(_text(vnext[0].get("content"))) if vnext else 0,
            }
        )

    compared = [row for row in rows if row["status"] == "COMPARED"]
    blocking_statuses = {"MISSING_PACKAGE", "PROFILE_NO_RESULT"}
    summary = {
        "status": "PASS" if compared and not any(row["status"] in blocking_statuses for row in rows) else "REVIEW",
        "tests_compared": len(compared),
        "status_counts": dict(Counter(row["status"] for row in rows)),
        "top_family_match_rate": round(
            sum(bool(row["top_family_match"]) for row in compared) / max(1, len(compared)),
            4,
        ),
        "current_top_in_vnext_top5_rate": round(
            sum(bool(row["current_top_in_vnext_top5"]) for row in compared) / max(1, len(compared)),
            4,
        ),
        "current_top_in_vnext_top10_rate": round(
            sum(bool(row["current_top_in_vnext_top10"]) for row in compared) / max(1, len(compared)),
            4,
        ),
        "mean_top10_family_overlap": round(
            mean(float(row["top10_family_overlap"]) for row in compared),
            4,
        ) if compared else 0.0,
        "mean_current_top_chars": round(
            mean(int(row["current_top_chars"]) for row in compared),
        ) if compared else 0,
        "mean_vnext_top_chars": round(
            mean(int(row["vnext_top_chars"]) for row in compared),
        ) if compared else 0,
    }
    return rows, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlsx", required=True, type=Path)
    parser.add_argument("--current-root", required=True, type=Path)
    parser.add_argument("--vnext-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--sheet", default="Test Cases")
    parser.add_argument("--header-row", default=3, type=int)
    parser.add_argument("--top-k", default=10, type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows, summary = compare(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / "retrieval-profile-comparison.csv"
    json_path = args.output_dir / "retrieval-profile-summary.json"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = list(rows[0]) if rows else []
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        if rows:
            writer.writeheader()
            writer.writerows(rows)
    json_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"CSV: {csv_path}")
    print(f"JSON: {json_path}")
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
