"""Merge bounded retry rows into a completed profile-evaluation report."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_paraphrase_profile_evaluation import summarize_profile, write_reports  # noqa: E402


def merge_reports(base: dict[str, Any], corrections: dict[str, Any]) -> dict[str, Any]:
    """Replace matching case IDs and recompute all aggregate metrics."""
    correction_rows = {str(row["id"]): row for row in corrections.get("cases", [])}
    if not correction_rows:
        raise ValueError("The correction report does not contain any cases.")
    base_ids = {str(row["id"]) for row in base.get("cases", [])}
    unknown = sorted(correction_rows.keys() - base_ids)
    if unknown:
        raise ValueError(f"Correction report contains unknown case IDs: {', '.join(unknown)}")

    rows = [correction_rows.get(str(row["id"]), row) for row in base["cases"]]
    correction_manifest = corrections.get("manifest", {})
    manifest = {
        **base["manifest"],
        "normalization_changes": correction_manifest.get(
            "normalization_changes",
            base["manifest"].get("normalization_changes", []),
        ),
        "corrected_case_ids": sorted(correction_rows),
        "correction_manifest": correction_manifest,
    }
    return {
        "manifest": manifest,
        "summary": {
            "current": summarize_profile(rows, "current"),
            "candidate": summarize_profile(rows, "candidate"),
        },
        "cases": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--corrections", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    base = json.loads(args.base.read_text(encoding="utf-8"))
    corrections = json.loads(args.corrections.read_text(encoding="utf-8"))
    merged = merge_reports(base, corrections)
    write_reports(args.output_dir, merged)
    (args.output_dir / "manifest.json").write_text(
        json.dumps(merged["manifest"], indent=2) + "\n",
        encoding="utf-8",
    )
    normalized_candidates = [
        args.corrections.parent / "normalized-fixture.json",
        args.base.parent / "normalized-fixture.json",
    ]
    for normalized_fixture in normalized_candidates:
        if normalized_fixture.exists():
            shutil.copyfile(
                normalized_fixture,
                args.output_dir / "normalized-fixture.json",
            )
            break
    print(json.dumps(merged["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
