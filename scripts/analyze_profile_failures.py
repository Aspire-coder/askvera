"""Classify retrieval-profile failures without rerunning model or search calls.

The profile evaluator records candidate recall, evidence selection, approval,
and final delivery separately.  This script turns those measurements into a
small failure taxonomy so retrieval changes can be scoped to the layer that
actually failed.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


PROFILE_NAMES = ("current", "candidate")


def classify_profile(profile: dict[str, Any], expected_behavior: str = "answer") -> str:
    """Return the earliest failed pipeline layer for one profile result."""
    status = str(profile.get("answer_status") or "")
    failure_layer = str(profile.get("failure_layer") or "")
    metrics = profile.get("candidate_metrics") or {}
    candidate_count = int(metrics.get("candidate_count") or 0)

    if expected_behavior == "abstain":
        return "unsafe_delivery" if profile.get("answer_delivered") is True else "expected_abstention"

    if status == "blocked_by_governance" or failure_layer == "governance":
        return "governance_block"
    if candidate_count == 0:
        return "no_candidates"
    if metrics.get("recall_at_20") is False:
        return "relevant_candidate_missing_top20"
    if profile.get("selector_success") is False:
        return "selector_miss"
    if profile.get("evidence_approved") is False:
        return "evidence_gate_rejection"
    if profile.get("answer_delivered") is False:
        return failure_layer or "answer_delivery_failure"
    return "delivered"


def repeat_is_stable(profile: dict[str, Any]) -> bool:
    """Report whether repeated retrieval snapshots agree on key outcomes."""
    repeats = profile.get("retrieval_repeats") or []
    if len(repeats) <= 1:
        return True
    signatures = {
        (
            snapshot.get("selector_success"),
            (snapshot.get("candidate_metrics") or {}).get("first_relevant_rank"),
            tuple(snapshot.get("document_sections") or []),
        )
        for snapshot in repeats
    }
    return len(signatures) == 1


def analyze_report(report: dict[str, Any]) -> dict[str, Any]:
    """Return case-level classifications and aggregate counts."""
    cases: list[dict[str, Any]] = []
    counts = {profile: Counter() for profile in PROFILE_NAMES}
    unstable = {profile: [] for profile in PROFILE_NAMES}

    for case in report.get("cases") or []:
        row: dict[str, Any] = {
            "id": case.get("id"),
            "category": case.get("category"),
            "country": case.get("country"),
            "language": case.get("language"),
            "question": case.get("question"),
            "expected_behavior": case.get("expected_behavior", "answer"),
        }
        for profile_name in PROFILE_NAMES:
            profile = case.get(profile_name) or {}
            classification = classify_profile(profile, str(row["expected_behavior"]))
            stable = repeat_is_stable(profile)
            counts[profile_name][classification] += 1
            if not stable:
                unstable[profile_name].append(case.get("id"))
            row[profile_name] = {
                "classification": classification,
                "stable": stable,
                "first_relevant_rank": (profile.get("candidate_metrics") or {}).get(
                    "first_relevant_rank"
                ),
                "selector_success": profile.get("selector_success"),
                "evidence_approved": profile.get("evidence_approved"),
                "answer_delivered": profile.get("answer_delivered"),
                "failure_layer": profile.get("failure_layer"),
            }
        cases.append(row)

    return {
        "manifest": report.get("manifest") or {},
        "counts": {name: dict(counts[name]) for name in PROFILE_NAMES},
        "unstable_case_ids": unstable,
        "cases": cases,
    }


def render_markdown(analysis: dict[str, Any]) -> str:
    """Render a compact human-reviewable failure report."""
    lines = ["# Retrieval Failure Analysis", ""]
    for profile_name in PROFILE_NAMES:
        lines.extend([f"## {profile_name.title()}", "", "| Classification | Cases |", "|---|---:|"])
        for classification, count in sorted((analysis["counts"].get(profile_name) or {}).items()):
            lines.append(f"| {classification} | {count} |")
        unstable = analysis["unstable_case_ids"].get(profile_name) or []
        lines.extend(["", f"Unstable repeated cases: {', '.join(unstable) if unstable else 'None'}", ""])

    lines.extend(
        [
            "## Case-level results",
            "",
            "| Case | Current | Candidate | Current stable | Candidate stable |",
            "|---|---|---|---:|---:|",
        ]
    )
    for case in analysis["cases"]:
        lines.append(
            "| {id} | {current} | {candidate} | {current_stable} | {candidate_stable} |".format(
                id=case["id"],
                current=case["current"]["classification"],
                candidate=case["candidate"]["classification"],
                current_stable="yes" if case["current"]["stable"] else "no",
                candidate_stable="yes" if case["candidate"]["stable"] else "no",
            )
        )
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = json.loads(args.input.read_text(encoding="utf-8"))
    analysis = analyze_report(report)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "failure-analysis.json").write_text(
        json.dumps(analysis, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "failure-analysis.md").write_text(
        render_markdown(analysis),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
