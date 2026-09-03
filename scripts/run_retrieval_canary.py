"""Run the blocking retrieval canary against the configured active index."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# This canary is a blocking, batch, pre-deploy quality gate, not a live user
# request - it can afford a couple of retries on a transient Bedrock blip,
# unlike the deliberately zero-retry client production uses so an
# interactive chat request never hangs through multiple backoff cycles. Must
# be set before `from config import settings` first runs in this process
# (settings.AWS_INTERACTIVE_MAX_ATTEMPTS is read once, at import time), and
# only affects this standalone script's own process - never the live
# askvera service, which is a separate process with its own environment.
os.environ.setdefault("AWS_INTERACTIVE_MAX_ATTEMPTS", "3")


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
        "document_scores": [round(float(document.score or 0.0), 3) for document in result.documents],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--load-ssm", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
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
    logging.disable(logging.INFO)
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
