"""Run the blocking retrieval canary against the configured active index."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, NamedTuple

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
# A conversation case costs one generation call per prior turn plus one for the
# question itself, on every deploy. Three is enough to reach a chained
# follow-up, which is the shape worth gating on.
MAX_CONVERSATION_TURNS = 3
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


def _validate_allowed_removed_numbers(case: dict[str, Any], identifier: str) -> None:
    if "answer_allowed_removed_numbers" not in case:
        return

    allowed_numbers = case["answer_allowed_removed_numbers"]
    if (
        not isinstance(allowed_numbers, list)
        or not allowed_numbers
        or any(not isinstance(number, str) or not number.strip() for number in allowed_numbers)
    ):
        raise ValueError(
            f"'answer_allowed_removed_numbers' must be a non-empty list of strings "
            f"for {identifier}."
        )
    if case.get("answer_must_not_remove_numbers"):
        raise ValueError(
            f"{identifier} cannot both forbid and allow numeric-claim removal."
        )


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
        if "conversation" in case:
            conversation = case["conversation"]
            if not isinstance(conversation, list) or not conversation:
                raise ValueError(f"'conversation' must be a non-empty list for {identifier}.")
            if any(
                not (
                    isinstance(turn, str) and turn.strip()
                    or isinstance(turn, dict) and str(turn.get("question") or "").strip()
                )
                for turn in conversation
            ):
                raise ValueError(f"'conversation' turns need non-empty questions for {identifier}.")
            # Each prior turn is a full generation call, so a conversation case
            # costs len(conversation) + 1 of them. The cap keeps one careless
            # fixture edit from multiplying every deploy's gate cost.
            if len(conversation) > MAX_CONVERSATION_TURNS:
                raise ValueError(
                    f"'conversation' for {identifier} exceeds {MAX_CONVERSATION_TURNS} turns."
                )
        if "blocking" in case and not isinstance(case["blocking"], bool):
            raise ValueError(f"'blocking' must be true or false for {identifier}.")
        _validate_allowed_removed_numbers(case, identifier)
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


def _numeric_removal_failures(case: dict[str, Any], removed_numbers: list[str]) -> list[str]:
    if bool(case.get("answer_must_not_remove_numbers")) and removed_numbers:
        return [f"grounding repair removed {removed_numbers} from the delivered answer"]

    allowed_numbers = set(case.get("answer_allowed_removed_numbers") or [])
    unexpected_numbers = sorted(set(removed_numbers) - allowed_numbers)
    if unexpected_numbers:
        return [
            "grounding repair removed unexpected numbers "
            f"{unexpected_numbers} from the delivered answer"
        ]
    return []


def _git_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


class _RecordingRetriever:
    """Wrap the retrieval service and remember what it handed the orchestrator.

    The gate used to call `RetrievalService.retrieve` itself and then run the
    pipeline separately, so the evidence it reported and the answer it checked
    came from two different executions and could disagree. Recording what the
    pipeline actually used makes them the same run.
    """

    def __init__(self, inner) -> None:
        self._inner = inner
        self.results = []

    def retrieve(self, *args, **kwargs):
        result = self._inner.retrieve(*args, **kwargs)
        self.results.append(result)
        return result

    @property
    def last(self):
        # The final retrieval is the one the delivered answer was built from;
        # earlier ones would belong to an abandoned branch.
        return self.results[-1] if self.results else None


class _CanaryTranscript:
    """In-memory stand-in for the session store, in its stored format.

    A batch gate has no real session, but a follow-up case has no meaning
    without one: the orchestrator reads prior turns out of history to work out
    what a bare "Tell me more" is actually asking about.

    The format matches services.session exactly - two lines per turn, with
    newlines flattened inside each message. That flattening is not cosmetic: an
    answer containing a line beginning "user:" would otherwise be read back as
    a prior turn the reader never sent.
    """

    def __init__(self) -> None:
        self._messages: list[str] = []

    def history(self, *args, **kwargs) -> str:
        return "\n".join(self._messages)

    def append(self, session_id, user_message, vera_response, correlation_id=None) -> None:
        for line in (f"user: {user_message}", f"vera: {vera_response}"):
            self._messages.append(" ".join(line.splitlines()))


def _canary_patches(transcript: "_CanaryTranscript | None" = None) -> dict:
    """Stubs applied to the orchestrator module for the duration of one run.

    Session and consent are stubbed because a batch gate has no real session.
    When a transcript is supplied, history is served from it instead of being
    empty, so a multi-turn case can be replayed and a follow-up judged against
    what actually came before it.

    The caches are stubbed for a more important reason. `handle_chat` consults
    the exact cache and then the semantic cache before doing any work, so a
    repeated case would run the pipeline once and read cache for every run
    after that -- making `--repeat`, which exists to expose flakiness,
    partially inert on exactly the delivered-answer cases that matter most.
    A quality gate has to measure the pipeline, not the cache.

    The writes are stubbed too, so the gate leaves no trace in the production
    cache. Previously each deploy seeded real cache entries with canary
    answers.
    """
    return {
        "validate_and_touch_session": lambda *args, **kwargs: None,
        "has_valid_consent": lambda *args, **kwargs: True,
        "get_session_history": (
            transcript.history if transcript else (lambda *args, **kwargs: "")
        ),
        "append_session_turn": (
            transcript.append if transcript else (lambda *args, **kwargs: None)
        ),
        "get_cache_value": lambda *args, **kwargs: None,
        "set_cache_value": lambda *args, **kwargs: None,
        "semantic_cache_active": lambda *args, **kwargs: False,
        "get_semantic_cache_value": lambda *args, **kwargs: None,
        "set_semantic_cache_value": lambda *args, **kwargs: None,
    }


class _PipelineRun(NamedTuple):
    """Everything one real run produced, for whichever caller needs it.

    The canary only needs the answer and the figures repair removed. The
    benchmark also needs token counts and how the answer ended, so it can
    price a run and tell a refusal apart from a reply. Both read the same
    execution rather than each having their own.
    """

    retrieval: Any
    response: Any
    removed_numeric_claims: list[str]
    duration_ms: float
    prior_responses: tuple[Any, ...] = ()


def run_pipeline_capture(case: dict[str, Any], sequence: int) -> _PipelineRun:
    """Run the real pipeline once and return the retrieval it used and the answer.

    Retrieval scoring cannot see what happens after a document is selected. On
    2026-09-07 every defect found after the selector regression lived downstream
    of it - in governance, output validation and numeric repair - and this canary
    passed 15/15 while a rank-qualification question failed in production:
    correct, cited answers were discarded, or delivered with the governing figure
    silently removed.

    Everything from retrieval onward runs exactly as it does for a user,
    including generation, validation, repair and output governance.
    """
    from app.orchestrator import chat_orchestrator
    from app.retrieval.service import RetrievalService
    from utils.validators import ChatRequest

    transcript = _CanaryTranscript()
    patched = _canary_patches(transcript)
    originals = {name: getattr(chat_orchestrator, name) for name in patched}
    for name, replacement in patched.items():
        setattr(chat_orchestrator, name, replacement)

    session_id = f"deployment-canary-{sequence}"
    recorder = _RecordingRetriever(RetrievalService())

    def ask(message: str, label: str):
        return chat_orchestrator.AIOrchestrator(retriever=recorder).handle_chat(
            ChatRequest(
                message=message,
                sessionId=session_id,
                country=str(case["country"]),
                language=str(case["language"]),
                role=str(case["role"]),
            ),
            f"deployment-canary-answer-{sequence}-{case['id']}-{label}",
        )

    started = time.perf_counter()
    try:
        # Prior turns are replayed through the real pipeline so the follow-up
        # is judged against history the orchestrator itself produced, rather
        # than a hand-written transcript that could drift from what the system
        # actually says. Each one costs a generation call, which is why
        # conversation cases are opt-in and few.
        prior_responses = []
        for index, prior_turn in enumerate(case.get("conversation") or []):
            message = prior_turn if isinstance(prior_turn, str) else prior_turn["question"]
            prior_responses.append(ask(str(message), f"turn{index}"))

        # Assertions apply to the final question only. The recorder's last
        # retrieval belongs to it for the same reason.
        response = ask(str(case["question"]), "final")
        # Grounding repair silently edits an answer before the reader sees it,
        # and the removed figures are the only record of what was taken out.
        # Surfacing them lets a case assert that nothing was removed, which is
        # far more robust than guessing how a model will format a time.
        removed = list((response.metadata or {}).get("removed_numeric_claims") or [])
        return _PipelineRun(
            recorder.last, response, removed, round((time.perf_counter() - started) * 1000, 1),
            tuple(prior_responses),
        )
    finally:
        for name, original in originals.items():
            setattr(chat_orchestrator, name, original)


def run_pipeline_once(case: dict[str, Any], sequence: int):
    """Answer-shaped view of one run, kept as the gate's own entry point."""
    run = run_pipeline_capture(case, sequence)
    response = run.response
    return (
        run.retrieval,
        response.answer or "",
        len(response.citations or []),
        run.removed_numeric_claims,
    )


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
    """Evaluate one case against one execution of the pipeline."""
    from app.evidence import approve_evidence
    from app.retrieval.service import RetrievalService

    question = str(case["question"])
    answer_required = [str(value) for value in (case.get("answer_must_contain") or [])]
    answer_forbidden = [str(value) for value in (case.get("answer_must_not_contain") or [])]
    checks_answer = bool(answer_required or answer_forbidden or case.get("answer_must_cite"))
    # A conversation case has to go through the pipeline even when it asserts
    # only on retrieval, because prior turns are replayed there and nowhere
    # else. Routing it to the retrieval-only path would run the final question
    # with no history at all and score it as a first turn -- a multi-turn case
    # that silently stopped being one, which is worse than not having it.
    uses_pipeline = (
        checks_answer
        or bool(case.get("conversation"))
        or bool(case.get("answer_must_not_remove_numbers"))
        or "answer_allowed_removed_numbers" in case
    )

    answer = ""
    answer_citations = -1
    removed_numbers: list[str] = []
    if uses_pipeline:
        # One execution supplies both the evidence and the answer, so a case
        # can never report retrieval from a run that produced a different reply.
        result, answer, answer_citations, removed_numbers = run_pipeline_once(case, sequence)
    else:
        # Retrieval-only cases skip generation entirely; it costs a model call
        # and proves nothing they assert.
        result = RetrievalService().retrieve(
            question,
            str(case["country"]),
            str(case["language"]),
            str(case["role"]),
            f"deployment-canary-{sequence}-{case['id']}",
        )

    failures: list[str] = []
    if result is None:
        # The pipeline answered without retrieving - an early conversational
        # route, a refusal, or a guardrail block. Reported rather than crashed,
        # because "this question no longer reaches retrieval" is a real
        # regression and an exception would hide it behind a stack trace.
        failures.append("pipeline returned an answer without performing retrieval")
        documents = []
        confidence = 0.0
        decision = None
    else:
        documents = result.documents
        confidence = float(result.confidence)
        decision = approve_evidence(
            question,
            result,
            str(case["country"]),
            str(case["language"]),
        )

    top_title = documents[0].title if documents else ""
    top_section = str(documents[0].metadata.get("section_id") or "") if documents else ""

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
    if bool(case["evidence_must_be_approved"]) and not (decision and decision.approved):
        reason = decision.reason if decision else "no retrieval performed"
        failures.append(f"evidence rejected: {reason}")
    if bool(case.get("evidence_must_be_absent")) and documents:
        failures.append(f"expected no evidence but received {len(documents)} documents")

    if checks_answer:
        folded = answer.casefold()
        for required in answer_required:
            if required.casefold() not in folded:
                failures.append(f"delivered answer is missing {required!r}")
        for forbidden in answer_forbidden:
            if forbidden.casefold() in folded:
                failures.append(f"delivered answer contains {forbidden!r}")
        if bool(case.get("answer_must_cite")) and answer_citations < 1:
            failures.append("delivered answer has no citation")

    # Checked outside the answer-assertion block: a case may care only that
    # repair left the answer alone. Office hours were being deleted from
    # directory answers over a notation difference, and no assertion about the
    # answer's text could catch that reliably, because the figures are simply
    # gone rather than wrong.
    failures.extend(_numeric_removal_failures(case, removed_numbers))

    return {
        "id": case["id"],
        "passed": not failures,
        "confidence": round(confidence, 3),
        "top_title": top_title,
        "top_section": top_section,
        "evidence_approved": bool(decision and decision.approved),
        "failure_reasons": failures,
        "typo_ranking_applied": bool(result.metadata.get("typo_ranking_applied")) if result else False,
        "ranking_query_used": result.metadata.get("ranking_query_used", "") if result else "",
        "document_scores": [round(float(document.score or 0.0), 3) for document in documents],
        "answer_citations": answer_citations,
        "answer_extract": answer[:200],
        "removed_numeric_claims": removed_numbers,
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
