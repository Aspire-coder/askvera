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
        if "blocking" in case and not isinstance(case["blocking"], bool):
            raise ValueError(f"'blocking' must be true or false for {identifier}.")
        if "repeat" in case:
            repeat = case["repeat"]
            if not isinstance(repeat, int) or isinstance(repeat, bool) or repeat < 1:
                raise ValueError(f"'repeat' must be a positive integer for {identifier}.")
        # A non-blocking case needs a stated reason, so the quarantine list
        # cannot quietly become the place failures go to be forgotten.
        if case.get("blocking") is False and not str(case.get("non_blocking_reason") or "").strip():
            raise ValueError(
                f"Case {identifier} is non-blocking and must set 'non_blocking_reason'."
            )
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


def delivered_answer(case: dict[str, Any], sequence: int) -> tuple[str, int]:
    """Return the answer a user would actually receive, and its citation count.

    Retrieval scoring cannot see what happens after a document is selected. On
    2026-09-07 every defect found after the selector regression lived downstream
    of it - in governance, output validation and numeric repair - and this canary
    passed 15/15 while a rank-qualification question failed in production:
    correct, cited answers were discarded, or delivered with the governing figure
    silently removed.

    Session and consent are stubbed because a batch gate has no real session. The
    rest of the pipeline runs exactly as it does for a user, including generation,
    validation, repair and output governance.
    """
    from app.orchestrator import chat_orchestrator
    from utils.validators import ChatRequest

    patched = {
        "validate_and_touch_session": lambda *args, **kwargs: None,
        "has_valid_consent": lambda *args, **kwargs: True,
        "get_session_history": lambda *args, **kwargs: "",
        "append_session_turn": lambda *args, **kwargs: None,
    }
    originals = {name: getattr(chat_orchestrator, name) for name in patched}
    for name, replacement in patched.items():
        setattr(chat_orchestrator, name, replacement)
    try:
        response = chat_orchestrator.AIOrchestrator().handle_chat(
            ChatRequest(
                message=str(case["question"]),
                sessionId=f"deployment-canary-{sequence}",
                country=str(case["country"]),
                language=str(case["language"]),
                role=str(case["role"]),
            ),
            f"deployment-canary-answer-{sequence}-{case['id']}",
        )
        return response.answer or "", len(response.citations or [])
    finally:
        for name, original in originals.items():
            setattr(chat_orchestrator, name, original)


def run_case(case: dict[str, Any], sequence: int, default_repeat: int) -> dict[str, Any]:
    """Run one case repeatedly and require every run to pass.

    A single run of a case that fails one time in three is close to
    meaningless, and reporting it as a pass trains everyone to retry a red
    deploy until it goes green -- which is how a real regression gets waved
    through. Repeating turns an intermittent failure into a visible one.

    A case that passes some runs and fails others is reported as flaky rather
    than simply failed, because the two want different responses: a flaky case
    means the pipeline is non-deterministic on that input, while a uniformly
    failed case means it is reliably wrong.
    """
    repeat = max(1, int(case.get("repeat") or default_repeat))
    runs = [run_case_once(case, sequence * 1000 + attempt) for attempt in range(repeat)]

    passed_runs = sum(1 for run in runs if run["passed"])
    # Report the first failing run, so failure_reasons describe an actual
    # observed failure rather than a run that happened to succeed.
    representative = next((run for run in runs if not run["passed"]), runs[0])

    blocking = bool(case.get("blocking", True))
    result = dict(representative)
    result.update(
        {
            "passed": passed_runs == repeat,
            "blocking": blocking,
            "runs": repeat,
            "passed_runs": passed_runs,
            "flaky": 0 < passed_runs < repeat,
        }
    )
    return result


def run_case_once(case: dict[str, Any], sequence: int):
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

    # Optional second stage: what the user is actually shown. Costs one
    # generation call, so it is opt-in per case rather than run for all of them.
    answer_required = [str(value) for value in (case.get("answer_must_contain") or [])]
    answer_forbidden = [str(value) for value in (case.get("answer_must_not_contain") or [])]
    answer_extract = ""
    answer_citations = -1
    if answer_required or answer_forbidden or case.get("answer_must_cite"):
        answer, answer_citations = delivered_answer(case, sequence)
        answer_extract = answer[:200]
        folded = answer.casefold()
        for required in answer_required:
            if required.casefold() not in folded:
                failures.append(f"delivered answer is missing {required!r}")
        for forbidden in answer_forbidden:
            if forbidden.casefold() in folded:
                failures.append(f"delivered answer contains {forbidden!r}")
        if bool(case.get("answer_must_cite")) and answer_citations < 1:
            failures.append("delivered answer has no citation")

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
        "answer_citations": answer_citations,
        "answer_extract": answer_extract,
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
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help=(
            "Runs per case; a case passes only if every run passes. Each run costs "
            "real Bedrock calls, so the deploy gate uses 1 and this is for "
            "investigating whether a case is genuinely stable."
        ),
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
    results = [run_case(case, index, args.repeat) for index, case in enumerate(cases, start=1)]

    # Only blocking cases decide the exit code. Non-blocking cases are observed
    # and reported so a known-unstable case keeps producing evidence instead of
    # being deleted, without holding up a deploy that is otherwise sound.
    blocking_results = [result for result in results if result["blocking"]]
    blocking_failures = [result for result in blocking_results if not result["passed"]]
    observed_failures = [
        result for result in results if not result["blocking"] and not result["passed"]
    ]
    summary = {
        "status": "passed" if not blocking_failures else "failed",
        "commit": _git_commit(),
        "index": settings.OPENSEARCH_INDEX,
        "pipeline_version": settings.RETRIEVAL_PIPELINE_VERSION,
        "fixture_sha256": fixture_hash,
        "runs_per_case": args.repeat,
        "passed": sum(result["passed"] for result in blocking_results),
        "total": len(blocking_results),
        "observed_only_cases": len(results) - len(blocking_results),
        "observed_only_failures": [result["id"] for result in observed_failures],
        "flaky_cases": [result["id"] for result in results if result["flaky"]],
        "results": results,
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
