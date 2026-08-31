"""Run the blocking retrieval canary against the configured active index."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "retrieval_canary.json"
REQUIRED_CASE_FIELDS = {
    "id",
    "question",
    "country",
    "language",
    "role",
    "expected_title_contains",
    "minimum_confidence",
    "evidence_must_be_approved",
}
VNEXT_FACTORS = {
    "authority": "RETRIEVAL_VNEXT_AUTHORITY_RANKING_ENABLED",
    "parent-child": "RETRIEVAL_VNEXT_PARENT_CHILD_ENABLED",
    "signal-confidence": "RETRIEVAL_VNEXT_SIGNAL_CONFIDENCE_ENABLED",
    "target-market-guard": "RETRIEVAL_VNEXT_TARGET_MARKET_GUARD_ENABLED",
    "rrf": "RETRIEVAL_VNEXT_RRF_ENABLED",
    "parent-diversity": "RETRIEVAL_VNEXT_PARENT_DIVERSITY_ENABLED",
    "evidence-selector": "RETRIEVAL_VNEXT_EVIDENCE_SELECTOR_ENABLED",
    "hardening": "RETRIEVAL_VNEXT_HARDENING_ENABLED",
    "rerank": "RETRIEVAL_VNEXT_RERANK_ENABLED",
}
VNEXT_PROFILES = ("authority-parent", "authority-stack")


def _mirror_current_retrieval_factors() -> None:
    """Make the isolated provider behave like the live provider before adding a delta."""
    from config import settings

    settings.RETRIEVAL_VNEXT_RRF_ENABLED = False
    settings.RETRIEVAL_VNEXT_PARENT_DIVERSITY_ENABLED = False
    settings.RETRIEVAL_VNEXT_AUTHORITY_RANKING_ENABLED = bool(
        settings.RETRIEVAL_AUTHORITY_RANKING_ENABLED
    )
    settings.RETRIEVAL_VNEXT_PARENT_CHILD_ENABLED = bool(
        settings.RETRIEVAL_PARENT_CHILD_ENABLED
    )
    settings.RETRIEVAL_VNEXT_SIGNAL_CONFIDENCE_ENABLED = bool(
        settings.RETRIEVAL_SIGNAL_CONFIDENCE_ENABLED
    )
    settings.RETRIEVAL_VNEXT_TARGET_MARKET_GUARD_ENABLED = bool(
        settings.RETRIEVAL_TARGET_MARKET_GUARD_ENABLED
    )
    settings.RETRIEVAL_VNEXT_EVIDENCE_SELECTOR_ENABLED = bool(
        settings.OPENSEARCH_EVIDENCE_SELECTOR_ENABLED
    )
    settings.RETRIEVAL_VNEXT_HARDENING_ENABLED = bool(
        settings.OPENSEARCH_RETRIEVAL_HARDENING_ENABLED
    )
    settings.RETRIEVAL_VNEXT_RERANK_ENABLED = False


def load_fixture(path: Path) -> tuple[list[dict[str, Any]], str]:
    raw = path.read_bytes()
    payload = json.loads(raw)
    if payload.get("schema_version") != 1 or not isinstance(payload.get("cases"), list):
        raise ValueError("Retrieval canary fixture must use schema_version 1 and contain a cases list.")
    cases = payload["cases"]
    if not cases:
        raise ValueError("Retrieval canary fixture must contain at least one case.")
    identifiers: set[str] = set()
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict) or not REQUIRED_CASE_FIELDS.issubset(case):
            raise ValueError(f"Retrieval canary case {index} is missing required fields.")
        identifier = str(case["id"]).strip()
        if not identifier or identifier in identifiers:
            raise ValueError(f"Retrieval canary case IDs must be non-empty and unique: {identifier!r}.")
        identifiers.add(identifier)
        minimum_confidence = float(case["minimum_confidence"])
        if not 0.0 <= minimum_confidence <= 1.0:
            raise ValueError(f"Invalid minimum confidence for {identifier}: {minimum_confidence}.")
    return cases, hashlib.sha256(raw).hexdigest()


def _git_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def configure_vnext_experiment(
    *,
    index_name: str = "",
    factor: str = "configured",
) -> None:
    """Apply explicit candidate overrides after SSM has loaded."""
    from config import settings

    if index_name:
        settings.OPENSEARCH_VNEXT_INDEX = index_name
    if factor == "configured":
        return
    if factor not in {"none", "parity", *VNEXT_FACTORS, *VNEXT_PROFILES}:
        raise ValueError(f"Unsupported vNext factor: {factor}")
    if factor == "none":
        for setting_name in VNEXT_FACTORS.values():
            setattr(settings, setting_name, False)
        return
    _mirror_current_retrieval_factors()
    if factor in {"authority-parent", "authority-stack"}:
        settings.RETRIEVAL_VNEXT_AUTHORITY_RANKING_ENABLED = True
        settings.RETRIEVAL_VNEXT_PARENT_CHILD_ENABLED = True
        settings.RETRIEVAL_VNEXT_SIGNAL_CONFIDENCE_ENABLED = factor == "authority-stack"
        settings.RETRIEVAL_VNEXT_TARGET_MARKET_GUARD_ENABLED = True
    elif factor != "parity":
        setattr(settings, VNEXT_FACTORS[factor], True)


def _provider_for_profile(profile: str):
    """Build one explicit provider so a canary never starts background Shadow work."""
    from app.retrieval.service import RetrievalService
    from config import settings

    if profile == "current":
        return RetrievalService._provider_for_name(settings.RETRIEVAL_PROVIDER)
    if (
        not settings.OPENSEARCH_VNEXT_INDEX
        or settings.OPENSEARCH_VNEXT_INDEX == settings.OPENSEARCH_INDEX
    ):
        raise ValueError("The vNext canary requires an isolated OPENSEARCH_VNEXT_INDEX.")
    return RetrievalService._provider_for_name(
        settings.RETRIEVAL_VNEXT_PROVIDER,
        index_name=settings.OPENSEARCH_VNEXT_INDEX,
        enable_bedrock_rerank=settings.RETRIEVAL_VNEXT_RERANK_ENABLED,
        enable_rrf=settings.RETRIEVAL_VNEXT_RRF_ENABLED,
        enable_parent_diversity=settings.RETRIEVAL_VNEXT_PARENT_DIVERSITY_ENABLED,
        enable_authority_ranking=settings.RETRIEVAL_VNEXT_AUTHORITY_RANKING_ENABLED,
        enable_parent_child=settings.RETRIEVAL_VNEXT_PARENT_CHILD_ENABLED,
        enable_signal_confidence=settings.RETRIEVAL_VNEXT_SIGNAL_CONFIDENCE_ENABLED,
        enable_target_market_guard=settings.RETRIEVAL_VNEXT_TARGET_MARKET_GUARD_ENABLED,
        enable_evidence_selector=settings.RETRIEVAL_VNEXT_EVIDENCE_SELECTOR_ENABLED,
        enable_retrieval_hardening=settings.RETRIEVAL_VNEXT_HARDENING_ENABLED,
        profile_name="vnext",
    )


def run_case(case: dict[str, Any], sequence: int, provider=None):
    from app.evidence import approve_evidence

    provider = provider or _provider_for_profile("current")
    question = str(case["question"])
    result = provider.retrieve(
        question,
        str(case["country"]),
        str(case["language"]),
        str(case["role"]),
        f"deployment-canary-{sequence}-{case['id']}",
    )
    decision = approve_evidence(
        question,
        result,
        str(case["country"]),
        str(case["language"]),
    )
    top_title = result.documents[0].title if result.documents else ""
    top_section = (
        str(result.documents[0].metadata.get("section_id") or "")
        if result.documents
        else ""
    )
    confidence = float(result.confidence)
    failures: list[str] = []
    expected_title = str(case["expected_title_contains"])
    if expected_title and expected_title.casefold() not in top_title.casefold():
        failures.append(f"top title {top_title!r} does not contain {expected_title!r}")
    expected_section = str(case.get("expected_section_contains") or "")
    if expected_section and expected_section.casefold() not in top_section.casefold():
        failures.append(
            f"top section {top_section!r} does not contain {expected_section!r}"
        )
    if confidence < float(case["minimum_confidence"]):
        failures.append(
            f"confidence {confidence:.3f} is below {float(case['minimum_confidence']):.3f}"
        )
    if bool(case["evidence_must_be_approved"]) and not decision.approved:
        failures.append(f"evidence rejected: {decision.reason}")
    if bool(case.get("evidence_must_be_absent")) and result.documents:
        failures.append(f"expected no evidence but received {len(result.documents)} documents")
    return {
        "id": case["id"],
        "passed": not failures,
        "confidence": round(confidence, 3),
        "top_title": top_title,
        "top_section": top_section,
        "evidence_approved": decision.approved,
        "failure_reasons": failures,
        "typo_ranking_applied": bool(result.metadata.get("typo_ranking_applied")),
        "ranking_query_used": result.metadata.get("ranking_query_used", ""),
        "retrieval_profile": result.metadata.get("retrieval_profile", "current"),
        "fusion_strategy": result.metadata.get("fusion_strategy", ""),
        "candidate_count": int(result.metadata.get("candidate_count") or 0),
        "selected_candidate_count": int(result.metadata.get("selected_candidate_count") or 0),
        "threshold_eligible_count": int(result.metadata.get("threshold_eligible_count") or 0),
        "selector_rejected": bool(result.metadata.get("evidence_selector_rejected")),
        "document_scores": [round(float(document.score or 0.0), 3) for document in result.documents],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--load-ssm", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument(
        "--profile",
        choices=("current", "vnext"),
        default="current",
        help="Evaluate Current or the isolated vNext candidate. Current remains the default.",
    )
    parser.add_argument(
        "--vnext-index",
        default="",
        help="Override OPENSEARCH_VNEXT_INDEX after SSM loads.",
    )
    parser.add_argument(
        "--vnext-factor",
        choices=("configured", "none", "parity", *VNEXT_FACTORS, *VNEXT_PROFILES),
        default="configured",
        help="Enable exactly one candidate factor, or none, after SSM loads.",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="Run only the named case. Repeat this option to run a bounded subset.",
    )
    args = parser.parse_args()

    try:
        cases, fixture_hash = load_fixture(args.fixture)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Retrieval canary fixture is invalid: {exc}", file=sys.stderr)
        return 2

    if args.validate_only:
        print(json.dumps({"status": "valid", "cases": len(cases), "fixture_sha256": fixture_hash}))
        return 0

    if args.case_id:
        requested_ids = set(args.case_id)
        available_ids = {str(case["id"]) for case in cases}
        unknown_ids = sorted(requested_ids - available_ids)
        if unknown_ids:
            print(f"Unknown retrieval canary case IDs: {', '.join(unknown_ids)}", file=sys.stderr)
            return 2
        cases = [case for case in cases if str(case["id"]) in requested_ids]

    from config import settings

    if args.load_ssm:
        settings.load_ssm_config()
    configure_vnext_experiment(
        index_name=args.vnext_index,
        factor=args.vnext_factor,
    )
    logging.disable(logging.INFO)
    try:
        provider = _provider_for_profile(args.profile)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    results = [
        run_case(case, index, provider)
        for index, case in enumerate(cases, start=1)
    ]
    evaluated_index = (
        settings.OPENSEARCH_VNEXT_INDEX
        if args.profile == "vnext"
        else settings.OPENSEARCH_INDEX
    )
    pipeline_version = (
        settings.RETRIEVAL_VNEXT_PIPELINE_VERSION
        if args.profile == "vnext"
        else settings.RETRIEVAL_PIPELINE_VERSION
    )
    summary = {
        "status": "passed" if all(result["passed"] for result in results) else "failed",
        "commit": _git_commit(),
        "profile": args.profile,
        "index": evaluated_index,
        "pipeline_version": pipeline_version,
        "vnext_factor": args.vnext_factor,
        "fixture_sha256": fixture_hash,
        "passed": sum(result["passed"] for result in results),
        "total": len(results),
        "results": results,
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
