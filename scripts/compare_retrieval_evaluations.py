"""Compare current and vNext evaluation checkpoints case by case."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


def _load_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        row = json.loads(line)
        case_id = str(row.get("case_id") or "").strip()
        if not case_id:
            raise ValueError(f"{path}:{line_number} has no case_id")
        if case_id in rows:
            raise ValueError(f"{path} contains duplicate case_id {case_id}")
        rows[case_id] = row
    return rows


def _documents(row: dict[str, Any], key: str) -> list[dict[str, Any]]:
    return list((row.get(key) or {}).get("documents") or [])


def _status(row: dict[str, Any], key: str) -> str:
    return str((row.get(key) or {}).get("status") or "MISSING")


def compare_rows(
    current: dict[str, dict[str, Any]],
    vnext: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    shared = sorted(
        current.keys() & vnext.keys(),
        key=lambda case_id: int(current[case_id].get("case_index") or 0),
    )
    transitions: Counter[str] = Counter()
    details: list[dict[str, Any]] = []
    top_matches = 0
    retrieval_pairs = 0
    overlap_total = 0
    for case_id in shared:
        current_row = current[case_id]
        vnext_row = vnext[case_id]
        current_status = _status(current_row, "current_answer")
        vnext_status = _status(vnext_row, "vnext_answer")
        transitions[f"{current_status} -> {vnext_status}"] += 1
        current_docs = _documents(current_row, "current_retrieval")
        vnext_docs = _documents(vnext_row, "vnext_retrieval")
        current_ids = [str(document.get("id") or "") for document in current_docs]
        vnext_ids = [str(document.get("id") or "") for document in vnext_docs]
        overlap = len(set(current_ids) & set(vnext_ids))
        top_match = bool(
            current_ids and vnext_ids and current_ids[0] == vnext_ids[0]
        )
        if current_ids or vnext_ids:
            retrieval_pairs += 1
            overlap_total += overlap
            top_matches += int(top_match)
        comparison = "same_outcome"
        if current_status != "APPROVED" and vnext_status == "APPROVED":
            comparison = "vnext_approved_current_not"
        elif current_status == "APPROVED" and vnext_status != "APPROVED":
            comparison = "current_approved_vnext_not"
        elif current_status != vnext_status:
            comparison = "different_nonapproval_outcome"
        details.append(
            {
                "case_index": current_row.get("case_index", ""),
                "case_id": case_id,
                "country": current_row.get("country", ""),
                "language": current_row.get("language", ""),
                "question": current_row.get("question", ""),
                "comparison": comparison,
                "current_answer_status": current_status,
                "vnext_answer_status": vnext_status,
                "top_result_matches": top_match,
                "result_overlap": overlap,
                "current_top_source": current_ids[0] if current_ids else "",
                "vnext_top_source": vnext_ids[0] if vnext_ids else "",
                "current_source_ids": " | ".join(current_ids),
                "vnext_source_ids": " | ".join(vnext_ids),
            }
        )

    summary = {
        "matched_cases": len(shared),
        "current_only_cases": len(current.keys() - vnext.keys()),
        "vnext_only_cases": len(vnext.keys() - current.keys()),
        "answer_status_transitions": dict(transitions.most_common()),
        "vnext_approved_current_not": sum(
            detail["comparison"] == "vnext_approved_current_not"
            for detail in details
        ),
        "current_approved_vnext_not": sum(
            detail["comparison"] == "current_approved_vnext_not"
            for detail in details
        ),
        "retrieval_pairs": retrieval_pairs,
        "top_result_match_rate": round(top_matches / max(1, retrieval_pairs), 4),
        "mean_result_overlap": round(overlap_total / max(1, retrieval_pairs), 4),
    }
    return summary, details


def _write_reports(
    summary: dict[str, Any],
    details: list[dict[str, Any]],
    output_prefix: Path,
) -> tuple[Path, Path]:
    summary_path = output_prefix.with_name(output_prefix.name + "-summary.json")
    detail_path = output_prefix.with_name(output_prefix.name + "-cases.csv")
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    fields = list(details[0]) if details else []
    with detail_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if fields:
            writer.writeheader()
            writer.writerows(details)
    return summary_path, detail_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--vnext", type=Path, required=True)
    parser.add_argument("--output-prefix", type=Path, required=True)
    args = parser.parse_args()
    summary, details = compare_rows(
        _load_jsonl(args.current),
        _load_jsonl(args.vnext),
    )
    summary_path, detail_path = _write_reports(
        summary,
        details,
        args.output_prefix,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"summary: {summary_path}")
    print(f"cases: {detail_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
