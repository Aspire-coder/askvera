"""Capture metadata-only retrieval diagnostics for selected frozen cases."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "retrieval_canary.json"


def _load_cases(path: Path, requested: set[str]) -> tuple[list[dict[str, Any]], str]:
    raw = path.read_bytes()
    payload = json.loads(raw)
    cases = [case for case in payload["cases"] if str(case["id"]) in requested]
    missing = sorted(requested - {str(case["id"]) for case in cases})
    if missing:
        raise ValueError(f"Unknown case IDs: {', '.join(missing)}")
    return cases, hashlib.sha256(raw).hexdigest()


def _plan_snapshot(plan: Any) -> dict[str, Any]:
    return {
        "queries": list(plan.queries or []),
        "include_global_documents": bool(plan.include_global_documents),
        "prefer_outline": bool(plan.prefer_outline),
        "conversation_intent": str(plan.conversation_intent or ""),
        "conversation_subtype": str(plan.conversation_subtype or ""),
        "intent_confidence": float(plan.intent_confidence or 0.0),
    }


def _result_snapshot(result: Any, decision: Any) -> dict[str, Any]:
    metadata = dict(result.metadata or {})
    return {
        "confidence": round(float(result.confidence or 0.0), 6),
        "evidence_approved": bool(decision.approved),
        "evidence_reason": str(decision.reason or ""),
        "top_documents": [
            {
                "rank": index,
                "title": str(document.title or ""),
                "section_id": str(document.metadata.get("section_id") or ""),
                "country": str(document.country or document.metadata.get("country") or ""),
                "record_country": str(document.metadata.get("record_country") or ""),
                "score": round(float(document.score or 0.0), 6),
            }
            for index, document in enumerate(result.documents[:20], start=1)
        ],
        "candidate_stages": metadata.get("candidate_stages") or {},
        "confidence_signals": metadata.get("confidence_signals") or {},
        "selector": {
            key: metadata.get(key)
            for key in (
                "evidence_selector_applied",
                "evidence_selector_rejected",
                "evidence_selector_selected_ranks",
                "evidence_selector_reason",
                "authority_anchor_preserved",
            )
            if key in metadata
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--load-ssm", action="store_true")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--case-id", action="append", required=True)
    parser.add_argument("--profile", choices=("current", "vnext"), default="current")
    parser.add_argument("--vnext-index", default="")
    parser.add_argument("--vnext-factor", default="parity")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    from app.evidence import approve_evidence
    from config import settings
    from scripts.run_retrieval_canary import (
        _provider_for_profile,
        configure_vnext_experiment,
    )

    logging.disable(logging.INFO)
    if args.load_ssm:
        settings.load_ssm_config()
    configure_vnext_experiment(
        index_name=args.vnext_index,
        factor=args.vnext_factor,
    )
    cases, fixture_hash = _load_cases(args.fixture, set(args.case_id))
    provider = _provider_for_profile(args.profile)
    captured_plans: dict[str, dict[str, Any]] = {}
    original_build_plan = provider._build_search_plan

    def capture_plan(message: str, country: str, language: str, correlation_id: str):
        plan = original_build_plan(message, country, language, correlation_id)
        captured_plans[correlation_id] = _plan_snapshot(plan)
        return plan

    provider._build_search_plan = capture_plan
    rows: list[dict[str, Any]] = []
    for case in cases:
        case_id = str(case["id"])
        correlation_id = f"diagnostic-{args.profile}-{case_id}"
        result = provider.retrieve(
            str(case["question"]),
            str(case["country"]),
            str(case["language"]),
            str(case["role"]),
            correlation_id,
        )
        decision = approve_evidence(
            str(case["question"]),
            result,
            str(case["country"]),
            str(case["language"]),
        )
        rows.append(
            {
                "case_id": case_id,
                "question": case["question"],
                "fixture_sha256": fixture_hash,
                "search_plan": captured_plans.get(correlation_id, {}),
                "result": _result_snapshot(result, decision),
            }
        )

    payload = {
        "profile": args.profile,
        "index": (
            settings.OPENSEARCH_INDEX
            if args.profile == "current"
            else settings.OPENSEARCH_VNEXT_INDEX
        ),
        "factor": args.vnext_factor if args.profile == "vnext" else "current",
        "cache": "bypassed",
        "cases": rows,
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
