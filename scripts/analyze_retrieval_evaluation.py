"""Produce reproducible statistical and segment reports for retrieval runs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from evaluate_interaction_history import (  # noqa: E402
    _best_expected_rank,
    _load_expected_evidence_labels,
)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _merge_profile_checkpoints(baseline_path: Path, candidate_path: Path) -> list[dict[str, Any]]:
    """Pair candidate snapshots from separate profile runs by immutable case ID."""
    baseline = {str(row["case_id"]): row for row in _load_jsonl(baseline_path)}
    candidate = {str(row["case_id"]): row for row in _load_jsonl(candidate_path)}
    merged: list[dict[str, Any]] = []
    for case_id in sorted(baseline.keys() & candidate.keys(), key=lambda value: int(baseline[value].get("case_index") or 0)):
        old = baseline[case_id]
        new = candidate[case_id]
        row = dict(old)
        row["vnext_retrieval"] = new.get("vnext_retrieval", {})
        row["vnext_answer"] = new.get("vnext_answer", {})
        merged.append(row)
    return merged


def _approved_labels(path: Path) -> dict[str, dict[str, Any]]:
    return {
        key: value
        for key, value in _load_expected_evidence_labels(path).items()
        if str(value.get("label_status") or "").casefold() == "approved"
    }


def _wilson(successes: int, total: int, z: float = 1.959963984540054) -> dict[str, float | None]:
    if total <= 0:
        return {"lower": None, "upper": None}
    proportion = successes / total
    denominator = 1.0 + (z * z / total)
    centre = (proportion + z * z / (2.0 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            (proportion * (1.0 - proportion) / total)
            + (z * z / (4.0 * total * total))
        )
        / denominator
    )
    return {
        "lower": round(max(0.0, centre - margin), 4),
        "upper": round(min(1.0, centre + margin), 4),
    }


def _rank(row: dict[str, Any], pipeline: str, label: dict[str, Any]) -> int | None:
    snapshot = row.get(f"{pipeline}_retrieval")
    if not isinstance(snapshot, dict):
        return None
    return _best_expected_rank(snapshot, label, match_scope="section")


def _bucket(row: dict[str, Any]) -> dict[str, str]:
    question = str(row.get("question") or "")
    lowered = question.casefold()
    tags = []
    if any(token in lowered for token in ("what is", "was ist", "qué es", "che cos")):
        tags.append("definition")
    if any(token in lowered for token in ("how", "wie", "cómo", "come", "comment")):
        tags.append("procedure_or_requirement")
    if re_search_number(question):
        tags.append("numeric")
    if any(token in lowered for token in ("must not", "cannot", "not allowed", "darf nicht", "nicht")):
        tags.append("restriction_or_exception")
    if any(token in lowered for token in ("section", "sec.", "§")):
        tags.append("explicit_section")
    if len(question.split()) <= 5:
        tags.append("short_or_ambiguous")
    return {
        "country": str(row.get("country") or "unknown"),
        "language": str(row.get("language") or "unknown"),
        "intent": str(
            (row.get("vnext_retrieval") or {}).get("conversation_intent")
            or (row.get("current_retrieval") or {}).get("conversation_intent")
            or "knowledge"
        ),
        "difficulty": "+".join(tags) if tags else "general",
    }


def re_search_number(value: str) -> bool:
    return any(character.isdigit() for character in value)


def _metric(ranks: list[int | None]) -> dict[str, Any]:
    total = len(ranks)
    values: dict[str, Any] = {"labeled_cases": total}
    for cutoff in (1, 3, 5, 10):
        successes = sum(rank is not None and rank <= cutoff for rank in ranks)
        values[f"recall_at_{cutoff}"] = round(successes / max(1, total), 4)
        values[f"recall_at_{cutoff}_ci95"] = _wilson(successes, total)
    values["mrr"] = round(
        sum(1.0 / rank for rank in ranks if rank is not None) / max(1, total),
        4,
    )
    return values


def _mcnemar(baseline: list[int | None], candidate: list[int | None], cutoff: int) -> dict[str, Any]:
    paired = [
        (old is not None and old <= cutoff, new is not None and new <= cutoff)
        for old, new in zip(baseline, candidate, strict=True)
    ]
    baseline_only = sum(old and not new for old, new in paired)
    candidate_only = sum(new and not old for old, new in paired)
    discordant = baseline_only + candidate_only
    tail = sum(math.comb(discordant, index) for index in range(min(baseline_only, candidate_only) + 1))
    p_value = min(1.0, 2.0 * tail / (2.0**discordant)) if discordant else 1.0
    return {
        "cutoff": cutoff,
        "paired_cases": len(paired),
        "baseline_correct_candidate_wrong": baseline_only,
        "candidate_correct_baseline_wrong": candidate_only,
        "exact_two_sided_p_value": round(p_value, 6),
    }


def analyze_rows(rows: list[dict[str, Any]], labels: dict[str, dict[str, Any]], baseline: str, candidate: str) -> dict[str, Any]:
    labeled = [row for row in rows if str(row.get("case_id") or "") in labels and labels[str(row.get("case_id"))].get("expected_section_ids")]
    baseline_ranks = [_rank(row, baseline, labels[str(row["case_id"])]) for row in labeled]
    candidate_ranks = [_rank(row, candidate, labels[str(row["case_id"])]) for row in labeled]
    groups: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(labeled):
        for dimension, value in _bucket(row).items():
            groups[f"{dimension}={value}"].append(index)
    segments = {}
    for name, indexes in sorted(groups.items()):
        segments[name] = {
            "baseline": _metric([baseline_ranks[index] for index in indexes]),
            "candidate": _metric([candidate_ranks[index] for index in indexes]),
        }
    return {
        "baseline_pipeline": baseline,
        "candidate_pipeline": candidate,
        "labeled_section_cases": len(labeled),
        "baseline": _metric(baseline_ranks),
        "candidate": _metric(candidate_ranks),
        "paired_tests": {
            f"recall_at_{cutoff}": _mcnemar(baseline_ranks, candidate_ranks, cutoff)
            for cutoff in (1, 3, 5, 10)
        },
        "segments": segments,
    }


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_breakdown(path: Path, analysis: dict[str, Any]) -> None:
    fields = ["segment", "baseline_recall_at_1", "candidate_recall_at_1", "baseline_recall_at_5", "candidate_recall_at_5", "cases"]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for segment, values in analysis["segments"].items():
            writer.writerow(
                {
                    "segment": segment,
                    "baseline_recall_at_1": values["baseline"]["recall_at_1"],
                    "candidate_recall_at_1": values["candidate"]["recall_at_1"],
                    "baseline_recall_at_5": values["baseline"]["recall_at_5"],
                    "candidate_recall_at_5": values["candidate"]["recall_at_5"],
                    "cases": values["baseline"]["labeled_cases"],
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument(
        "--baseline-checkpoint",
        type=Path,
        default=None,
        help="Optional separate baseline profile checkpoint; pairs by case_id.",
    )
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--baseline", default="current")
    parser.add_argument("--candidate", default="vnext")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--benchmark-version", default="unversioned")
    parser.add_argument("--index-name", default="unknown")
    parser.add_argument("--query-planner-version", default="unknown")
    parser.add_argument("--profile", default="unknown")
    args = parser.parse_args()
    rows = (
        _merge_profile_checkpoints(args.baseline_checkpoint, args.checkpoint)
        if args.baseline_checkpoint
        else _load_jsonl(args.checkpoint)
    )
    analysis = analyze_rows(rows, _approved_labels(args.labels), args.baseline, args.candidate)
    manifest = {
        "benchmark_version": args.benchmark_version,
        "checkpoint_sha256": _sha256(args.checkpoint),
        "labels_sha256": _sha256(args.labels),
        "checkpoint": str(args.checkpoint),
        "baseline_checkpoint": str(args.baseline_checkpoint) if args.baseline_checkpoint else None,
        "labels": str(args.labels),
        "index_name": args.index_name,
        "query_planner_version": args.query_planner_version,
        "ranking_profile": args.profile,
        "git_commit": _git_commit(),
        "analysis_timestamp_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }
    output = {"manifest": manifest, "analysis": analysis}
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_breakdown(args.output.with_name(args.output.stem + "-segments.csv"), analysis)
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
