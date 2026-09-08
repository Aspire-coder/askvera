"""Measure answer quality on source-verified questions.

This is not the retrieval canary and must not be confused with it. The canary
is a release gate built from failures we already found and fixed; passing it
proves we have not gone backwards. It cannot say how good the system is,
because every question in it is one somebody already repaired.

This runs questions the system has not been tuned against, records what it
actually delivered, and reports rates with stated denominators. A case may
legitimately expect an abstention: a question the approved documents do not
answer should be refused, and counting that as a failure would push the system
towards inventing answers.

Costs real money. Nothing here runs on a schedule, and --dry-run validates the
whole fixture without a single model call.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

# Same reasoning as the canary: a batch evaluation can afford a retry on a
# transient Bedrock blip, unlike an interactive request. Must be set before
# config.settings is first imported in this process.
os.environ.setdefault("AWS_INTERACTIVE_MAX_ATTEMPTS", "3")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "benchmark_cases.json"
REQUIRED_CASE_FIELDS = {"id", "question", "country", "language", "role", "intent_group", "expected"}
VALID_KINDS = {"answer", "abstain"}
# Every case has to say why its expectation is believed true. A benchmark whose
# ground truth is assumed measures the assumption, not the system.
REQUIRED_EVIDENCE_FIELDS = {"source_evidence", "provenance"}


def load_fixture(path: Path) -> tuple[list[dict[str, Any]], str]:
    """Load and validate benchmark cases, refusing anything unverifiable."""
    import hashlib

    raw = path.read_bytes()
    payload = json.loads(raw)
    if payload.get("schema_version") != 1 or not isinstance(payload.get("cases"), list):
        raise ValueError("Benchmark fixture must use schema_version 1 and contain a cases list.")
    cases = payload["cases"]
    if not cases:
        raise ValueError("Benchmark fixture must contain at least one case.")

    identifiers: set[str] = set()
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict) or not REQUIRED_CASE_FIELDS.issubset(case):
            missing = REQUIRED_CASE_FIELDS - set(case if isinstance(case, dict) else {})
            raise ValueError(f"Benchmark case {index} is missing required fields: {sorted(missing)}.")
        identifier = str(case["id"]).strip()
        if not identifier or identifier in identifiers:
            raise ValueError(f"Benchmark case IDs must be non-empty and unique: {identifier!r}.")
        identifiers.add(identifier)

        for field in REQUIRED_EVIDENCE_FIELDS:
            if not str(case.get(field) or "").strip():
                raise ValueError(
                    f"Case {identifier} must state {field!r}. A benchmark whose ground truth is "
                    "assumed measures the assumption, not the system."
                )

        expected = case["expected"]
        if not isinstance(expected, dict) or expected.get("kind") not in VALID_KINDS:
            raise ValueError(f"Case {identifier} needs expected.kind of {sorted(VALID_KINDS)}.")
        if expected["kind"] == "answer" and not expected.get("must_contain"):
            raise ValueError(
                f"Case {identifier} expects an answer but asserts nothing it must contain, "
                "so it would pass on any reply at all."
            )
        if "conversation" in case and (
            not isinstance(case["conversation"], list) or not case["conversation"]
        ):
            raise ValueError(f"'conversation' must be a non-empty list for {identifier}.")

    return cases, hashlib.sha256(raw).hexdigest()


# A refusal is only recognisable against the copy the system actually uses, and
# that copy is per-locale. Matching English text against a French answer scores
# a correct French refusal as a wrong answer, so every non-English case would
# report a failure the system did not commit.
_REFUSAL_KEYS = (
    "insufficient_evidence",
    "catalogue_scope",
    "off_topic",
    "medical_claim",
    "income_claim",
    "period_not_covered",
)


def _refusal_markers(language: str) -> list[str]:
    """Opening clauses of every approved way of declining, in one locale."""
    from app.evidence import localized_conversation_response

    markers = []
    for key in _REFUSAL_KEYS:
        copy = localized_conversation_response(key, language) or ""
        if copy:
            # The opening clause is the stable part; the tail names a contact
            # route that varies by market.
            markers.append(" ".join(copy.split())[:60].casefold())
    return markers


def _abstained(answer: str, language: str) -> bool:
    """Whether the delivered text declines rather than answers, in its own locale."""
    folded = " ".join((answer or "").split()).casefold()
    return any(marker and marker in folded for marker in _refusal_markers(language))


def _section_keys(pairs: list[tuple[str, str]]) -> list[str]:
    """Section identifiers, both bare and country-qualified.

    A case can then require "2-part-1-definition-18" when the section is
    unambiguous, or "DK:2-part-1-definition-18" when the same identifier exists
    in several markets and only one of them is the reader's.
    """
    keys: list[str] = []
    for section, country in pairs:
        if not section:
            continue
        keys.append(section)
        if country:
            keys.append(f"{country.upper()}:{section}")
    return keys


def run_case_once(canary, case: dict[str, Any], sequence: int) -> dict[str, Any]:
    """Run one question through the real pipeline and record what came back.

    The run itself is the canary's, deliberately. If the benchmark had its own
    copy of "ask this like a user would", the two could drift -- and the one
    that drifts is always the one nobody runs on every deploy.
    """
    run = canary.run_pipeline_capture(case, sequence)
    response = run.response
    metadata = response.metadata or {}
    usage = metadata.get("token_usage") or {}
    documents = run.retrieval.documents if run.retrieval else []
    answer = response.answer or ""

    return {
        "answer": answer,
        "citations": len(response.citations or []),
        "abstained": bool(metadata.get("fallback")) or _abstained(answer, str(case["language"])),
        "failure_layer": metadata.get("failure_layer") or "",
        # Why generation stopped. "max_tokens" is Bedrock stating it ran out of
        # room, which is a fact, unlike a heuristic reading of the text.
        "finish_reason": str(metadata.get("finish_reason") or ""),
        "removed_numeric_claims": run.removed_numeric_claims,
        "top_title": documents[0].title if documents else "",
        # Every retrieved section, so a case can require the governing one to
        # be present rather than merely first, and can say which sections the
        # answer was actually built from.
        #
        # Country-qualified keys are included because section IDs are not
        # unique across markets. "2-part-1-definition-18" is the FBO Support
        # fee in Denmark, Sweden, Norway and Finland - the same ID holding the
        # same 635 characters in four countries - and is "Forever Business
        # Owner (FBO)" in Canada. Matching on the ID alone cannot tell a Danish
        # reader's answer from Sweden's copy of it.
        "sections": _section_keys(
            [(str((d.metadata or {}).get("section_id") or ""), str(d.country or "")) for d in documents]
        ),
        # Citations are source dicts; "section" is the passage actually cited.
        "cited_sections": _section_keys(
            [
                (str((citation or {}).get("section") or ""), str((citation or {}).get("country") or ""))
                for citation in (response.citations or [])
            ]
        ),
        "confidence": round(float(run.retrieval.confidence), 3) if run.retrieval else 0.0,
        "input_tokens": int(usage.get("inputTokens") or 0),
        "output_tokens": int(usage.get("outputTokens") or 0),
        "duration_ms": run.duration_ms,
    }


def score_run(case: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    """Judge one run against the case's stated expectation."""
    expected = case["expected"]
    folded = " ".join(run["answer"].split()).casefold()
    failures: list[str] = []

    if expected["kind"] == "abstain":
        if not run["abstained"]:
            failures.append("answered a question the documents do not cover")
    else:
        if run["abstained"]:
            failures.append("abstained on an answerable question")
        for required in expected.get("must_contain") or []:
            if str(required).casefold() not in folded:
                failures.append(f"missing required fact {required!r}")
        if expected.get("must_cite") and run["citations"] < 1:
            failures.append("no citation")

    for forbidden in expected.get("must_not_contain") or []:
        if str(forbidden).casefold() in folded:
            failures.append(f"contains {forbidden!r}")

    # Retrieval is scored against section IDs when the case names them. A
    # title match is not evidence that the governing passage was found: the
    # sponsoring directory is one title covering every market, so "the right
    # document" can still be the wrong record entirely. A case that names no
    # source is left unscored for retrieval rather than counted as a success.
    required = [str(value) for value in (expected.get("required_sections") or [])]
    retrieved = set(run["sections"])
    cited = set(run["cited_sections"])
    if required:
        missing = [section for section in required if section not in retrieved]
        retrieval_hit = not missing
        if missing:
            failures.append(f"governing sections not retrieved: {missing}")
        # Citation correctness, not citation count: an answer can cite a real
        # passage that does not support what it says.
        if expected.get("must_cite"):
            uncited = [section for section in required if section not in cited]
            if not missing and uncited:
                failures.append(f"governing sections retrieved but not cited: {uncited}")
    else:
        title = str(expected.get("source_title_contains") or "")
        if title:
            retrieval_hit = title.casefold() in run["top_title"].casefold()
            if not retrieval_hit:
                failures.append(f"governing source not retrieved first: got {run['top_title']!r}")
        else:
            retrieval_hit = None

    return {
        **run,
        "passed": not failures,
        "failures": failures,
        "retrieval_hit": retrieval_hit,
        "repair_damaged": bool(run["removed_numeric_claims"]),
    }


def summarise(results: list[dict[str, Any]], rates: dict[str, float] | None) -> dict[str, Any]:
    """Report rates with their denominators stated, never a bare percentage."""
    runs = [run for case in results for run in case["runs"]]
    answerable = [
        run for case in results if case["expected_kind"] == "answer" for run in case["runs"]
    ]
    unanswerable = [
        run for case in results if case["expected_kind"] == "abstain" for run in case["runs"]
    ]

    def rate(numerator: int, denominator: int) -> str:
        return f"{numerator}/{denominator}" + (
            f" ({numerator / denominator:.1%})" if denominator else " (n/a)"
        )

    by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in results:
        by_group[case["intent_group"]].extend(case["runs"])

    input_tokens = sum(run["input_tokens"] for run in runs)
    output_tokens = sum(run["output_tokens"] for run in runs)
    summary = {
        "cases": len(results),
        "runs": len(runs),
        "stable_cases": sum(1 for case in results if case["passed_runs"] in (0, case["runs_count"])),
        "unstable_cases": [case["id"] for case in results if 0 < case["passed_runs"] < case["runs_count"]],
        "correct": rate(sum(1 for run in runs if run["passed"]), len(runs)),
        "false_abstention": rate(
            sum(1 for run in answerable if run["abstained"]), len(answerable)
        ),
        "answered_when_it_should_not": rate(
            sum(1 for run in unanswerable if not run["abstained"]), len(unanswerable)
        ),
        # Only cases that named a governing source are counted. Averaging in
        # cases that specified none would inflate the rate with unscored runs.
        "retrieval_hit": rate(
            sum(1 for run in runs if run["retrieval_hit"] is True),
            sum(1 for run in runs if run["retrieval_hit"] is not None),
        ),
        "retrieval_unscored": sum(1 for run in runs if run["retrieval_hit"] is None),
        "cited": rate(sum(1 for run in answerable if run["citations"] > 0), len(answerable)),
        "repair_damage": rate(sum(1 for run in runs if run["repair_damaged"]), len(runs)),
        "by_intent_group": {
            group: rate(sum(1 for run in group_runs if run["passed"]), len(group_runs))
            for group, group_runs in sorted(by_group.items())
        },
        "latency_ms_p50": round(statistics.median(run["duration_ms"] for run in runs), 1) if runs else 0,
        "latency_ms_max": round(max((run["duration_ms"] for run in runs), default=0), 1),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
    if rates:
        cost = input_tokens / 1_000_000 * rates["input"] + output_tokens / 1_000_000 * rates["output"]
        summary["measured_cost_usd"] = round(cost, 4)
        summary["cost_per_case_usd"] = round(cost / max(1, len(results)), 4)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--load-ssm", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Validate the fixture; make no model calls.")
    parser.add_argument("--limit", type=int, default=0, help="Run only the first N cases.")
    parser.add_argument("--intent-group", action="append", default=[], help="Restrict to these groups.")
    parser.add_argument("--repeat", type=int, default=3, help="Runs per case; stochastic stages need a distribution.")
    parser.add_argument("--artifact", type=Path, default=None, help="Write the full per-run record here.")
    parser.add_argument(
        "--input-usd-per-million", type=float, default=None,
        help="Your current Bedrock input price. Omit and the report gives tokens only.",
    )
    parser.add_argument("--output-usd-per-million", type=float, default=None)
    args = parser.parse_args()

    try:
        cases, fixture_hash = load_fixture(args.fixture)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Benchmark fixture is invalid: {exc}", file=sys.stderr)
        return 2

    if args.intent_group:
        wanted = set(args.intent_group)
        cases = [case for case in cases if case["intent_group"] in wanted]
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        print("No cases selected.", file=sys.stderr)
        return 2

    model_calls = sum((1 + len(case.get("conversation") or [])) for case in cases) * max(1, args.repeat)
    if args.dry_run:
        print(json.dumps({
            "status": "valid",
            "cases": len(cases),
            "runs": len(cases) * max(1, args.repeat),
            "generation_calls": model_calls,
            "fixture_sha256": fixture_hash,
            "note": "No model calls were made.",
        }, indent=2))
        return 0

    rates = None
    if args.input_usd_per_million is not None and args.output_usd_per_million is not None:
        rates = {"input": args.input_usd_per_million, "output": args.output_usd_per_million}

    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_retrieval_canary", PROJECT_ROOT / "scripts" / "run_retrieval_canary.py"
    )
    canary = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(canary)

    from config import settings

    if args.load_ssm:
        settings.load_ssm_config()
    logging.disable(logging.INFO)

    results = []
    for index, case in enumerate(cases, start=1):
        runs = []
        for attempt in range(max(1, args.repeat)):
            raw = run_case_once(canary, case, index * 1000 + attempt)
            runs.append(score_run(case, raw))
        passed_runs = sum(1 for run in runs if run["passed"])
        results.append({
            "id": case["id"],
            "question": case["question"],
            "intent_group": case["intent_group"],
            "expected_kind": case["expected"]["kind"],
            "provenance": case["provenance"],
            "runs_count": len(runs),
            "passed_runs": passed_runs,
            "runs": runs,
        })
        print(
            f"  {'ok  ' if passed_runs == len(runs) else 'FAIL'} "
            f"{passed_runs}/{len(runs)}  {case['id']}",
            file=sys.stderr,
        )

    summary = summarise(results, rates)
    summary.update({
        "index": settings.OPENSEARCH_INDEX,
        "pipeline_version": settings.RETRIEVAL_PIPELINE_VERSION,
        "fixture_sha256": fixture_hash,
        "repeat": max(1, args.repeat),
    })
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    if args.artifact:
        args.artifact.parent.mkdir(parents=True, exist_ok=True)
        args.artifact.write_text(
            json.dumps({"summary": summary, "cases": results}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"\nfull per-run record written to {args.artifact}", file=sys.stderr)

    # Reporting a measurement is the job; deciding whether it is good enough is
    # not. This never fails a build, unlike the canary.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
