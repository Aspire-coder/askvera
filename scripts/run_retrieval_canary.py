"""Run the blocking retrieval canary against the configured active index."""

from __future__ import annotations

import argparse
import hashlib
import json
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


def run_case(case: dict[str, Any], sequence: int):
    from app.evidence import approve_evidence
    from app.retrieval.service import RetrievalService

    service = RetrievalService()
    question = str(case["question"])
    result = service.retrieve(
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
    confidence = float(result.confidence)
    failures: list[str] = []
    expected_title = str(case["expected_title_contains"])
    if expected_title.casefold() not in top_title.casefold():
        failures.append(f"top title {top_title!r} does not contain {expected_title!r}")
    if confidence < float(case["minimum_confidence"]):
        failures.append(
            f"confidence {confidence:.3f} is below {float(case['minimum_confidence']):.3f}"
        )
    if bool(case["evidence_must_be_approved"]) and not decision.approved:
        failures.append(f"evidence rejected: {decision.reason}")
    return {
        "id": case["id"],
        "passed": not failures,
        "confidence": round(confidence, 3),
        "top_title": top_title,
        "evidence_approved": decision.approved,
        "failure_reasons": failures,
        "typo_ranking_applied": bool(result.metadata.get("typo_ranking_applied")),
        "ranking_query_used": result.metadata.get("ranking_query_used", ""),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--load-ssm", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    try:
        cases, fixture_hash = load_fixture(args.fixture)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Retrieval canary fixture is invalid: {exc}", file=sys.stderr)
        return 2

    if args.validate_only:
        print(json.dumps({"status": "valid", "cases": len(cases), "fixture_sha256": fixture_hash}))
        return 0

    from config import settings

    if args.load_ssm:
        settings.load_ssm_config()
    results = [run_case(case, index) for index, case in enumerate(cases, start=1)]
    summary = {
        "status": "passed" if all(result["passed"] for result in results) else "failed",
        "commit": _git_commit(),
        "index": settings.OPENSEARCH_INDEX,
        "pipeline_version": settings.RETRIEVAL_PIPELINE_VERSION,
        "fixture_sha256": fixture_hash,
        "passed": sum(result["passed"] for result in results),
        "total": len(results),
        "results": results,
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

