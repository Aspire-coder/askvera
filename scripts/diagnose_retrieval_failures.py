"""Classify reviewed retrieval misses from an evaluation checkpoint."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from evaluate_interaction_history import (  # noqa: E402
    _best_expected_rank,
    _load_expected_evidence_labels,
)


def _candidate_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {"documents": list(snapshot.get("candidate_evidence") or [])}


def diagnose_rows(
    rows: list[dict[str, Any]],
    labels: dict[str, dict[str, Any]],
    retrieval_key: str,
) -> list[dict[str, Any]]:
    """Return one diagnostic for labeled misses and every no-result row.

    No-result rows are included even when they have no evidence label because
    routing outcomes must be distinguished from genuine knowledge misses.
    """
    diagnostics: list[dict[str, Any]] = []
    for row in rows:
        label = labels.get(str(row.get("case_id") or ""))
        snapshot = dict(row.get(retrieval_key) or {})
        status = str(snapshot.get("status") or "")
        if (
            (not label or not label.get("expected_section_ids"))
            and status != "NO_RESULT"
        ):
            continue
        final_rank = (
            _best_expected_rank(snapshot, label, match_scope="section")
            if label
            else None
        )
        candidate_rank = (
            _best_expected_rank(
                _candidate_snapshot(snapshot),
                label,
                match_scope="section",
            )
            if label
            else None
        )
        intent = str(snapshot.get("conversation_intent") or "knowledge")
        if intent != "knowledge":
            classification = "INTENTIONALLY_ROUTED"
        elif status == "ERROR":
            classification = "RETRIEVAL_ERROR"
        elif final_rank == 1:
            classification = "TOP_1"
        elif final_rank is not None:
            classification = "FINAL_RANK_2_TO_5"
        elif candidate_rank is not None:
            classification = "CANDIDATE_NOT_IN_FINAL_5"
        else:
            classification = "NO_MATCHING_CANDIDATE"
        root_causes = {
            "INTENTIONALLY_ROUTED": "intentional_route",
            "RETRIEVAL_ERROR": "runtime_error",
            "TOP_1": "none",
            "FINAL_RANK_2_TO_5": "ranking_or_selection",
            "CANDIDATE_NOT_IN_FINAL_5": "threshold_or_final_selection",
            "NO_MATCHING_CANDIDATE": "planner_metadata_or_corpus_gap",
        }
        fix_candidates = {
            "INTENTIONALLY_ROUTED": "Validate route intent and response contract; no retrieval change.",
            "RETRIEVAL_ERROR": "Inspect dependency error and retry behavior.",
            "CANDIDATE_NOT_IN_FINAL_5": "Inspect final-score threshold and selection policy.",
            "NO_MATCHING_CANDIDATE": "Inspect planner queries, metadata scope, and corpus coverage.",
        }
        diagnostics.append(
            {
                "case_index": row.get("case_index", ""),
                "case_id": row.get("case_id", ""),
                "country": row.get("country", ""),
                "language": row.get("language", ""),
                "question": row.get("question", ""),
                "intent": intent,
                "intent_confidence": snapshot.get("intent_confidence", ""),
                "retrieval_status": status,
                "classification": classification,
                "root_cause": root_causes.get(classification, "needs_review"),
                "expected_evidence": " | ".join(
                    label.get("expected_section_ids") or []
                ) if label else "",
                "planner_queries": " | ".join(
                    snapshot.get("search_queries") or []
                ),
                "glossary_terms": " | ".join(
                    snapshot.get("glossary_queries") or []
                ),
                "raw_bm25_hits": "not captured by this checkpoint",
                "raw_vector_hits": "not captured by this checkpoint",
                "metadata_filters": "not captured by this checkpoint",
                "threshold_result": (
                    "not applicable: intentionally routed"
                    if classification == "INTENTIONALLY_ROUTED"
                    else "needs raw-hit trace"
                ),
                "fix_candidate": fix_candidates.get(classification, "Review case-level evidence."),
                "regression_risk": (
                    "Do not retrieve routed requests; preserve safety and intent boundaries."
                    if classification == "INTENTIONALLY_ROUTED"
                    else "Unknown until raw retrieval trace is captured."
                ),
                "final_rank": final_rank or "",
                "candidate_rank": candidate_rank or "",
                "expected_sections": " | ".join(
                    label.get("expected_section_ids") or []
                ) if label else "",
                "final_sections": " | ".join(
                    str(document.get("section") or "")
                    for document in snapshot.get("documents") or []
                ),
            }
        )
    return diagnostics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument(
        "--pipeline",
        choices=["current", "vnext"],
        default="current",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--no-results-only",
        action="store_true",
        help="Include only NO_RESULT rows, including intentional routing outcomes.",
    )
    args = parser.parse_args()

    rows = [
        json.loads(line)
        for line in args.checkpoint.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if args.no_results_only:
        rows = [
            row
            for row in rows
            if (row.get(f"{args.pipeline}_retrieval") or {}).get("status")
            == "NO_RESULT"
        ]
    diagnostics = diagnose_rows(
        rows,
        _load_expected_evidence_labels(args.labels),
        f"{args.pipeline}_retrieval",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(diagnostics[0]) if diagnostics else []
    with args.output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if fields:
            writer.writeheader()
            writer.writerows(diagnostics)
    counts: dict[str, int] = {}
    for row in diagnostics:
        key = str(row["classification"])
        counts[key] = counts.get(key, 0) + 1
    print(json.dumps({"count": len(diagnostics), "classifications": counts}, indent=2))
    print(f"output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
