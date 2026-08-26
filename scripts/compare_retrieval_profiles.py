"""Compare Current and isolated vNext retrieval against the same frozen fixture."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_retrieval_canary import (  # noqa: E402
    DEFAULT_FIXTURE,
    VNEXT_FACTORS,
    VNEXT_PROFILES,
    _provider_for_profile,
    configure_vnext_experiment,
    load_fixture,
    run_case,
)


def comparison_summary(
    current_results: list[dict[str, Any]],
    vnext_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Report exact improved and regressed case identities, not only totals."""
    current_by_id = {str(result["id"]): result for result in current_results}
    vnext_by_id = {str(result["id"]): result for result in vnext_results}
    shared_ids = sorted(current_by_id.keys() & vnext_by_id.keys())
    improved = [
        case_id
        for case_id in shared_ids
        if not current_by_id[case_id]["passed"] and vnext_by_id[case_id]["passed"]
    ]
    regressed = [
        case_id
        for case_id in shared_ids
        if current_by_id[case_id]["passed"] and not vnext_by_id[case_id]["passed"]
    ]
    current_passed = sum(bool(result["passed"]) for result in current_results)
    vnext_passed = sum(bool(result["passed"]) for result in vnext_results)
    return {
        "status": "passed" if not regressed and vnext_passed >= current_passed else "failed",
        "total": len(shared_ids),
        "current_passed": current_passed,
        "vnext_passed": vnext_passed,
        "improved_case_ids": improved,
        "regressed_case_ids": regressed,
        "unchanged_case_ids": [
            case_id
            for case_id in shared_ids
            if bool(current_by_id[case_id]["passed"]) == bool(vnext_by_id[case_id]["passed"])
        ],
    }


def _comparison_rows(
    current_results: list[dict[str, Any]],
    vnext_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    current_by_id = {str(result["id"]): result for result in current_results}
    rows: list[dict[str, Any]] = []
    for candidate in vnext_results:
        case_id = str(candidate["id"])
        current = current_by_id[case_id]
        rows.append(
            {
                "id": case_id,
                "current_passed": current["passed"],
                "vnext_passed": candidate["passed"],
                "outcome": (
                    "IMPROVED"
                    if not current["passed"] and candidate["passed"]
                    else "REGRESSED"
                    if current["passed"] and not candidate["passed"]
                    else "UNCHANGED"
                ),
                "current_top_title": current["top_title"],
                "vnext_top_title": candidate["top_title"],
                "current_top_section": current["top_section"],
                "vnext_top_section": candidate["top_section"],
                "current_confidence": current["confidence"],
                "vnext_confidence": candidate["confidence"],
                "current_evidence_approved": current["evidence_approved"],
                "vnext_evidence_approved": candidate["evidence_approved"],
                "vnext_fusion_strategy": candidate["fusion_strategy"],
                "vnext_candidate_count": candidate["candidate_count"],
                "vnext_selected_candidate_count": candidate["selected_candidate_count"],
                "vnext_threshold_eligible_count": candidate["threshold_eligible_count"],
                "vnext_selector_rejected": candidate["selector_rejected"],
                "current_failure_reasons": json.dumps(current["failure_reasons"]),
                "vnext_failure_reasons": json.dumps(candidate["failure_reasons"]),
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--load-ssm", action="store_true")
    parser.add_argument("--vnext-index", default="")
    parser.add_argument(
        "--vnext-factor",
        choices=("configured", "none", "parity", *VNEXT_FACTORS, *VNEXT_PROFILES),
        default="configured",
    )
    args = parser.parse_args()

    from config import settings

    if args.load_ssm:
        settings.load_ssm_config()
    configure_vnext_experiment(
        index_name=args.vnext_index,
        factor=args.vnext_factor,
    )
    cases, fixture_hash = load_fixture(args.fixture)
    logging.disable(logging.INFO)
    try:
        current_provider = _provider_for_profile("current")
        vnext_provider = _provider_for_profile("vnext")
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    current_results = [
        run_case(case, index, current_provider)
        for index, case in enumerate(cases, start=1)
    ]
    vnext_results = [
        run_case(case, index, vnext_provider)
        for index, case in enumerate(cases, start=1)
    ]
    summary = comparison_summary(current_results, vnext_results)
    summary.update(
        {
            "fixture": str(args.fixture),
            "fixture_sha256": fixture_hash,
            "current_index": settings.OPENSEARCH_INDEX,
            "vnext_index": settings.OPENSEARCH_VNEXT_INDEX,
            "current_pipeline_version": settings.RETRIEVAL_PIPELINE_VERSION,
            "vnext_pipeline_version": settings.RETRIEVAL_VNEXT_PIPELINE_VERSION,
            "vnext_factor": args.vnext_factor,
            "vnext_factor_state": {
                name: bool(getattr(settings, setting_name))
                for name, setting_name in VNEXT_FACTORS.items()
            },
        }
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows = _comparison_rows(current_results, vnext_results)
    csv_path = args.output_dir / "retrieval-profile-comparison.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)
    summary_path = args.output_dir / "retrieval-profile-summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
