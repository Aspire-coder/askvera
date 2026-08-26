"""Rescore saved profile reports after evaluation-label corrections.

This tool is deliberately offline: it does not call search, models, caches, or
AWS. It preserves the original report and writes a separate corrected artifact.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_paraphrase_profile_evaluation import (  # noqa: E402
    RETRIEVAL_DEPTHS,
    candidate_is_relevant,
    profile_meets_expectation,
    summarize_profile,
)


def _rescore_candidates(
    candidates: list[dict[str, Any]],
    case: dict[str, Any],
    candidate_count: int,
) -> dict[str, Any]:
    relevant_ranks = [
        index
        for index, candidate in enumerate(candidates, start=1)
        if candidate_is_relevant(candidate, case)
    ]
    first_rank = min(relevant_ranks) if relevant_ranks else None
    return {
        **{
            f"recall_at_{depth}": bool(first_rank and first_rank <= depth)
            for depth in RETRIEVAL_DEPTHS
        },
        "reciprocal_rank": round(1.0 / first_rank, 6) if first_rank else 0.0,
        "first_relevant_rank": first_rank,
        "candidate_count": candidate_count,
        "top_candidates": candidates,
    }


def _selected_is_relevant(
    selected_document_ids: list[str],
    candidates: list[dict[str, Any]],
    case: dict[str, Any],
) -> bool | None:
    if str(case.get("scope") or "") == "out_of_scope":
        return None
    selected_ids = {str(value) for value in selected_document_ids}
    return any(
        str(candidate.get("id") or "") in selected_ids
        and candidate_is_relevant(candidate, case)
        for candidate in candidates
    )


def rescore_report(report: dict[str, Any]) -> dict[str, Any]:
    """Return a corrected copy of one saved evaluator report."""
    corrected = json.loads(json.dumps(report))
    for case in corrected.get("cases") or []:
        # Early evaluator processes normalized every case as must-answer before
        # out-of-scope defaults were introduced. Scope is authoritative for
        # those safety cases, even when the stale report contains "answer".
        if str(case.get("scope") or "") == "out_of_scope":
            case["expected_behavior"] = "abstain"
        else:
            case.setdefault("expected_behavior", "answer")
        for profile_name in ("current", "candidate"):
            profile = case.get(profile_name) or {}
            metrics = profile.get("candidate_metrics") or {}
            candidates = list(metrics.get("top_candidates") or [])
            profile["candidate_metrics"] = _rescore_candidates(
                candidates,
                case,
                int(metrics.get("candidate_count") or len(candidates)),
            )

            repeats = profile.get("retrieval_repeats") or []
            for repeat in repeats:
                repeat_metrics = repeat.get("candidate_metrics") or {}
                repeat_candidates = list(repeat_metrics.get("top_candidates") or [])
                repeat["candidate_metrics"] = _rescore_candidates(
                    repeat_candidates,
                    case,
                    int(repeat_metrics.get("candidate_count") or len(repeat_candidates)),
                )
                repeat["selector_success"] = _selected_is_relevant(
                    list(repeat.get("document_ids") or []),
                    repeat_candidates,
                    case,
                )

            if repeats:
                profile["selector_success"] = repeats[0]["selector_success"]
            case[f"{profile_name}_expectation_met"] = profile_meets_expectation(
                SimpleNamespace(**profile),
                case,
            )

    corrected["summary"] = {
        profile_name: summarize_profile(corrected.get("cases") or [], profile_name)
        for profile_name in ("current", "candidate")
    }
    manifest = corrected.setdefault("manifest", {})
    manifest["offline_rescore"] = {
        "reason": (
            "Global-directory target country codes are matched to indexed country names, "
            "and out-of-scope cases are scored as must-abstain."
        ),
        "source_report_preserved": True,
    }
    return corrected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = json.loads(args.input.read_text(encoding="utf-8"))
    corrected = rescore_report(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(corrected, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
