"""Fail closed unless a retrieval evaluation satisfies promotion gates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def evaluate_gates(
    summary: dict[str, Any],
    *,
    min_recall_at_1: float = 0.8448,
    min_recall_at_5: float = 0.9828,
    min_recall_at_10: float = 0.9828,
    max_p95_latency_ms: float = 1500.0,
) -> dict[str, Any]:
    current = summary.get("current_retrieval") or {}
    candidate = summary.get("vnext_retrieval") or {}
    relevance = candidate.get("reviewed_section_relevance") or {}
    current_documents = current.get("reviewed_document_relevance") or {}
    candidate_documents = candidate.get("reviewed_document_relevance") or {}
    latency = (candidate.get("latency_ms") or {}).get("p95")
    checks = {
        "recall_at_1_strictly_improves_gate": float(relevance.get("recall_at_1") or 0.0)
        > min_recall_at_1,
        "recall_at_5_preserved": float(relevance.get("recall_at_5") or 0.0)
        >= min_recall_at_5,
        "recall_at_10_preserved": float(relevance.get("recall_at_10") or 0.0)
        >= min_recall_at_10,
        "document_recall_not_regressed": float(
            candidate_documents.get("recall_at_1") or 0.0
        )
        >= float(current_documents.get("recall_at_1") or 0.0),
        "no_new_retrieval_errors": int(
            (candidate.get("retrieval_coverage") or {}).get("retrieval_errors") or 0
        )
        <= int((current.get("retrieval_coverage") or {}).get("retrieval_errors") or 0),
        "latency_measured_and_acceptable": latency is not None
        and float(latency) <= max_p95_latency_ms,
    }
    return {
        "promote": all(checks.values()),
        "checks": checks,
        "candidate_metrics": {
            "recall_at_1": relevance.get("recall_at_1"),
            "recall_at_5": relevance.get("recall_at_5"),
            "recall_at_10": relevance.get("recall_at_10"),
            "p95_latency_ms": latency,
        },
        "thresholds": {
            "recall_at_1": f"> {min_recall_at_1}",
            "recall_at_5": f">= {min_recall_at_5}",
            "recall_at_10": f">= {min_recall_at_10}",
            "p95_latency_ms": f"<= {max_p95_latency_ms}",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-p95-latency-ms", type=float, default=1500.0)
    args = parser.parse_args()
    decision = evaluate_gates(
        json.loads(args.summary.read_text(encoding="utf-8")),
        max_p95_latency_ms=args.max_p95_latency_ms,
    )
    rendered = json.dumps(decision, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if decision["promote"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
