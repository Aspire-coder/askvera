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
import hashlib
import json
import logging
import os
import re
import statistics
import sys
from functools import lru_cache
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
VALID_EVALUATION_SETS = {"development", "held_out"}


@lru_cache(maxsize=1)
def _valid_roles() -> frozenset[str]:
    """Roles ChatRequest accepts, read from the same source it validates against."""
    from config.vera_persona import ROLE_CONTENT_SCOPES

    return frozenset(ROLE_CONTENT_SCOPES)


@lru_cache(maxsize=1)
def _valid_countries() -> frozenset[str]:
    """Enabled market codes, read from config rather than restated here."""
    payload = json.loads((PROJECT_ROOT / "config" / "markets.json").read_text(encoding="utf-8"))
    markets = payload.get("markets", payload) if isinstance(payload, dict) else payload
    return frozenset(
        str(market.get("code", "")).upper() for market in markets if market.get("enabled", True)
    )


def _chat_request_countries() -> frozenset[str]:
    """The request countries the chat API accepts, from the same source it uses.

    Not ``_valid_countries()``. That set is every enabled market in
    config/markets.json - 139 codes. ``ChatRequest`` accepts only enabled
    markets that are also in the published policy-locale catalog, through
    ``services.market_config.get_country_codes`` - 16 codes. Portugal is in the
    first and not the second, so a request checked against the broader set
    passed locally and was refused in production preflight as
    "Unsupported country". Imported here rather than at module load so the
    runner stays importable without application configuration.
    """
    from services.market_config import get_country_codes

    return frozenset(code.upper() for code in get_country_codes())


def _validate_patterns(identifier: str, expected: dict[str, Any], field: str) -> None:
    """Reject malformed regex expectations before a paid benchmark run."""
    patterns = expected.get(field, [])
    if not isinstance(patterns, list):
        raise ValueError(f"Case {identifier}: {field} must be a list.")
    for pattern in patterns:
        if not isinstance(pattern, str) or not pattern.strip():
            raise ValueError(f"Case {identifier}: {field} entries must be non-empty strings.")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"Case {identifier}: invalid {field} regex: {exc}") from exc


def _validate_held_out_readiness(payload: dict[str, Any], cases: list[Any]) -> None:
    """Do not run a draft held-out pack as though it were release evidence."""
    if not any(isinstance(case, dict) and case.get("evaluation_set") == "held_out" for case in cases):
        return
    from scripts.validate_held_out_release import validate

    errors = validate(payload)
    if errors:
        raise ValueError("Held-out fixture is not release-ready: " + "; ".join(errors))


def load_fixture(path: Path) -> tuple[list[dict[str, Any]], str]:  # noqa: C901
    """Load and validate benchmark cases, refusing anything unverifiable."""
    raw = path.read_bytes()
    payload = json.loads(raw)
    if payload.get("schema_version") != 1 or not isinstance(payload.get("cases"), list):
        raise ValueError("Benchmark fixture must use schema_version 1 and contain a cases list.")
    cases = payload["cases"]
    if not cases:
        raise ValueError("Benchmark fixture must contain at least one case.")
    _validate_held_out_readiness(payload, cases)

    identifiers: set[str] = set()
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict) or not REQUIRED_CASE_FIELDS.issubset(case):
            missing = REQUIRED_CASE_FIELDS - set(case if isinstance(case, dict) else {})
            raise ValueError(f"Benchmark case {index} is missing required fields: {sorted(missing)}.")
        identifier = str(case["id"]).strip()
        if not identifier or identifier in identifiers:
            raise ValueError(f"Benchmark case IDs must be non-empty and unique: {identifier!r}.")
        identifiers.add(identifier)

        evaluation_set = case.get("evaluation_set", "development")
        if evaluation_set not in VALID_EVALUATION_SETS:
            raise ValueError(
                f"Case {identifier} needs evaluation_set of {sorted(VALID_EVALUATION_SETS)}."
            )

        for field in REQUIRED_EVIDENCE_FIELDS:
            if not str(case.get(field) or "").strip():
                raise ValueError(
                    f"Case {identifier} must state {field!r}. A benchmark whose ground truth is "
                    "assumed measures the assumption, not the system."
                )

        if case["role"] not in _valid_roles():
            raise ValueError(
                f"Case {identifier} uses role {case['role']!r}, which ChatRequest rejects. "
                f"Supported roles: {sorted(_valid_roles())}."
            )
        country = str(case["country"]).strip().upper()
        if country not in _valid_countries():
            raise ValueError(f"Case {identifier} uses country {country!r}, which is not an enabled market.")

        expected = case["expected"]
        if not isinstance(expected, dict) or expected.get("kind") not in VALID_KINDS:
            raise ValueError(f"Case {identifier} needs expected.kind of {sorted(VALID_KINDS)}.")
        if (
            expected["kind"] == "answer"
            and not expected.get("must_contain")
            and not expected.get("required_patterns")
        ):
            raise ValueError(
                f"Case {identifier} expects an answer but asserts nothing it must contain, "
                "so it would pass on any reply at all."
            )
        _validate_patterns(identifier, expected, "required_patterns")
        _validate_patterns(identifier, expected, "forbidden_patterns")
        if "conversation" in case:
            turns = case["conversation"]
            if not isinstance(turns, list) or not turns:
                raise ValueError(f"'conversation' must be a non-empty list for {identifier}.")
            if len(turns) > 3:
                raise ValueError(f"Conversation for {identifier} exceeds three prior turns.")
            for turn in turns:
                if isinstance(turn, str) and turn.strip():
                    continue
                if isinstance(turn, dict) and str(turn.get("question") or "").strip():
                    turn_expected = turn.get("expected") or {}
                    if not isinstance(turn_expected, dict):
                        raise ValueError(f"Conversation expectation for {identifier} must be an object.")
                    _validate_patterns(identifier, turn_expected, "required_patterns")
                    _validate_patterns(identifier, turn_expected, "forbidden_patterns")
                    continue
                raise ValueError(f"Conversation turns for {identifier} need a non-empty question.")

    return cases, hashlib.sha256(raw).hexdigest()


def load_transport_overrides(
    path: Path | None, cases: list[dict[str, Any]], fixture_hash: str
) -> tuple[dict[str, str], str | None]:
    """Load a hash-bound request-country overlay for held-out execution.

    The source country remains the benchmark's ground truth. The overlay only
    selects a supported chat session and never changes a case's expectation.
    It has two mappings, kept separate so neither weakens the other:

    * ``request_countries`` - a globally scoped directory case whose own market
      is not enabled as an interactive AskVera market;
    * ``abstention_request_countries`` - a cross-market *refusal* case whose
      frozen session country is not a published market. Every condition it
      must meet is listed on ``_abstention_request_country``.

    One mapping is returned for execution: which mapping admitted a case does
    not matter once it has been validated.
    """
    if path is None:
        return {}, None

    raw = path.read_bytes()
    payload = json.loads(raw)
    if payload.get("schema_version") != 1:
        raise ValueError("Transport overrides must use schema_version 1.")
    if payload.get("fixture_sha256") != fixture_hash:
        raise ValueError("Transport overrides do not match the frozen fixture hash.")
    requested = payload.get("request_countries")
    if not isinstance(requested, dict):
        raise ValueError("Transport overrides need a request_countries object.")
    abstentions = payload.get("abstention_request_countries", {})
    if not isinstance(abstentions, dict):
        raise ValueError("Transport overrides' abstention_request_countries must be an object.")

    cases_by_id = {str(case["id"]): case for case in cases}
    overrides: dict[str, str] = {}
    for identifier, request_country in requested.items():
        if not isinstance(identifier, str) or identifier not in cases_by_id:
            raise ValueError(f"Transport override names an unknown case: {identifier!r}.")
        case = cases_by_id[identifier]
        source = case.get("source")
        if not isinstance(source, dict) or str(source.get("country", "")).upper() != "GLOBAL":
            raise ValueError(
                f"Transport override for {identifier} is forbidden: only GLOBAL source cases may use one."
            )
        country = str(request_country).strip().upper()
        if country not in _valid_countries():
            raise ValueError(
                f"Transport override for {identifier} uses unsupported request country {country!r}."
            )
        overrides[identifier] = country

    for identifier, request_country in abstentions.items():
        overrides[identifier] = _abstention_request_country(
            identifier, request_country, cases_by_id, overrides
        )

    return overrides, hashlib.sha256(raw).hexdigest()


def _abstention_request_country(
    identifier: object,
    request_country: object,
    cases_by_id: dict[str, dict[str, Any]],
    global_overrides: dict[str, str],
) -> str:
    """Admit one cross-market refusal to a supported session, or refuse loudly.

    Written for held-out case 23. A Portugal session asking for Italy's
    Cliente Premium commission must be refused, but ``PT`` is not a published
    market, so the request cannot be sent as frozen. Sending it from ``US``
    keeps it a cross-market question. Each condition exists so this exception
    cannot be used to change what a case measures:

    1. the case exists in the frozen fixture;
    2. it is not already transported by ``request_countries``;
    3. it has a local-policy source, not GLOBAL directory content, which has
       its own mapping;
    4. it expects a refusal - an answer case could be flipped into passing;
    5. it is cross-market: its source market differs from its frozen session;
    6. its frozen session is not a published market - a case that can run as
       frozen must run as frozen;
    7. the request country is a published market;
    8. the request country is not the source market. Asking for Italy's policy
       from an Italian session makes it an in-market question, which is
       exactly the claim that Portugal inherits Italian policy.
    """
    if not isinstance(identifier, str) or identifier not in cases_by_id:
        raise ValueError(f"Transport override names an unknown case: {identifier!r}.")
    if identifier in global_overrides:
        raise ValueError(
            f"Abstention transport for {identifier} is forbidden: it already has a "
            "request_countries transport."
        )
    case = cases_by_id[identifier]
    source = case.get("source")
    source_country = str(source.get("country", "")).upper() if isinstance(source, dict) else ""
    if not source_country:
        raise ValueError(f"Abstention transport for {identifier} is forbidden: the case names no source market.")
    if source_country == "GLOBAL":
        raise ValueError(
            f"Abstention transport for {identifier} is forbidden: GLOBAL source cases use request_countries."
        )
    expected = case.get("expected")
    if not isinstance(expected, dict) or expected.get("kind") != "abstain":
        raise ValueError(
            f"Abstention transport for {identifier} is forbidden: only abstention cases may use it."
        )
    session_country = str(case.get("country", "")).upper()
    if source_country == session_country:
        raise ValueError(f"Abstention transport for {identifier} is forbidden: it is not a cross-market case.")
    supported = _chat_request_countries()
    if session_country in supported:
        raise ValueError(
            f"Abstention transport for {identifier} is forbidden: its frozen request country "
            f"{session_country!r} is already supported."
        )
    country = str(request_country).strip().upper()
    if country not in supported:
        raise ValueError(
            f"Transport override for {identifier} uses unsupported request country {country!r}."
        )
    if country == source_country:
        raise ValueError(
            f"Abstention transport for {identifier} is forbidden: requesting from the source market "
            f"{country!r} would make it an in-market question."
        )
    return country


def execution_case_for_request(
    case: dict[str, Any], transport_overrides: dict[str, str]
) -> tuple[dict[str, Any], str]:
    """Return a request-only copy without changing the source-bound case."""
    request_country = transport_overrides.get(str(case["id"]), str(case["country"]).upper())
    return {**case, "country": request_country}, request_country


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


def _pattern_failures(expected: dict[str, Any], answer: str) -> list[str]:
    return [
        f"missing required pattern {pattern!r}"
        for pattern in expected.get("required_patterns") or []
        if re.search(pattern, answer, re.IGNORECASE) is None
    ]


def _prior_turn_failures(case: dict[str, Any], responses: tuple[Any, ...]) -> list[str]:
    """Score each structured follow-up turn the fixture explicitly evaluates."""
    failures: list[str] = []
    for number, (turn, response) in enumerate(zip(case.get("conversation") or [], responses), 1):
        if not isinstance(turn, dict) or not isinstance(turn.get("expected"), dict):
            continue
        expected = turn["expected"]
        answer = str(getattr(response, "answer", "") or "")
        abstained = bool((getattr(response, "metadata", None) or {}).get("fallback")) or _abstained(
            answer, str(turn.get("language") or case["language"])
        )
        if expected.get("kind", "answer") == "abstain":
            if not abstained:
                failures.append(f"turn {number}: answered a question the documents do not cover")
            continue
        if abstained:
            failures.append(f"turn {number}: abstained on an answerable question")
        for required in expected.get("must_contain") or []:
            if str(required).casefold() not in answer.casefold():
                failures.append(f"turn {number}: missing required fact {required!r}")
        failures.extend(f"turn {number}: {failure}" for failure in _pattern_failures(expected, answer))
        for pattern in expected.get("forbidden_patterns") or []:
            if re.search(pattern, answer, re.IGNORECASE):
                failures.append(f"turn {number}: contains forbidden pattern {pattern!r}")
    return failures


def _is_cited(required: str, cited: set[str]) -> bool:
    """Whether a citation covers the required section, including via its parent.

    A retrieved document is keyed by its own section_id, but a citation reports
    parent_section_id when there is one - the governing section a reader would
    look up, rather than the chunk the passage happens to sit in. So a correct
    citation for "2-part-1-definition-18" reads "2".

    Comparing the two as though they shared a namespace made the DK and SE
    scope cases fail for three runs while the system was doing exactly the right
    thing: retrieving each market's own copy of identical text and citing its
    governing section. The measurement was wrong, not the answer.

    The separator is required, so "2" covers "2-part-1-definition-18" and does
    not cover "21.05".
    """
    for key in cited:
        if key == required:
            return True
        if required.startswith(f"{key}-") or required.startswith(f"{key}."):
            return True
    return False


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


def _presence(numbers: list[str], documents: list[Any]) -> dict[str, bool]:
    """Which removed figures the retrieved documents actually contain."""
    from app.validation.validators.numeric_grounding_validator import numbers_present_in_sources

    return numbers_present_in_sources(numbers, documents) if numbers else {}


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
        "turn_failures": _prior_turn_failures(case, run.prior_responses),
        "citations": len(response.citations or []),
        "abstained": bool(metadata.get("fallback")) or _abstained(answer, str(case["language"])),
        "failure_layer": metadata.get("failure_layer") or "",
        # Why generation stopped. "max_tokens" is Bedrock stating it ran out of
        # room, which is a fact, unlike a heuristic reading of the text.
        "finish_reason": str(metadata.get("finish_reason") or ""),
        "removed_numeric_claims": run.removed_numeric_claims,
        # Repair removing a figure is not automatically damage. A number the
        # record does not contain was invented, and removing it is the system
        # working; a number the record does contain was real, and losing it
        # costs the reader a fact. Counting both as "damage" reports a number
        # that means nothing, and today both happened: Algeria's invented "50"
        # and Belgium's real "16" and "3743" would have scored identically.
        "removed_but_present_in_source": [
            number
            for number, present in _presence(run.removed_numeric_claims, documents).items()
            if present
        ],
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
        "generation_input_tokens": int(usage.get("inputTokens") or 0),
        "generation_output_tokens": int(usage.get("outputTokens") or 0),
        "duration_ms": run.duration_ms,
    }


def score_run(case: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:  # noqa: C901
    """Judge one run against the case's stated expectation."""
    expected = case["expected"]
    folded = " ".join(run["answer"].split()).casefold()
    failures: list[str] = []
    failures.extend(run.get("turn_failures") or [])

    if expected["kind"] == "abstain":
        if not run["abstained"]:
            failures.append("answered a question the documents do not cover")
    else:
        if run["abstained"]:
            failures.append("abstained on an answerable question")
        for required in expected.get("must_contain") or []:
            if str(required).casefold() not in folded:
                failures.append(f"missing required fact {required!r}")
        failures.extend(_pattern_failures(expected, run["answer"]))
        if expected.get("must_cite") and run["citations"] < 1:
            failures.append("no citation")

    for forbidden in expected.get("must_not_contain") or []:
        if str(forbidden).casefold() in folded:
            failures.append(f"contains {forbidden!r}")
    for pattern in expected.get("forbidden_patterns") or []:
        if re.search(pattern, run["answer"], re.IGNORECASE):
            failures.append(f"contains forbidden pattern {pattern!r}")

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
            uncited = [section for section in required if not _is_cited(section, cited)]
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
        # Damage is a supported figure removed, not any removal at all.
        "repair_removed_anything": bool(run["removed_numeric_claims"]),
        "repair_damaged": bool(run["removed_but_present_in_source"]),
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

    generation_input = sum(run["generation_input_tokens"] for run in runs)
    generation_output = sum(run["generation_output_tokens"] for run in runs)
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
        "repair_fired": rate(sum(1 for run in runs if run["repair_removed_anything"]), len(runs)),
        "repair_removed_supported_figure": rate(
            sum(1 for run in runs if run["repair_damaged"]), len(runs)
        ),
        "repair_removed_invented_figure": rate(
            sum(
                1
                for run in runs
                if run["repair_removed_anything"] and not run["repair_damaged"]
            ),
            len(runs),
        ),
        "by_intent_group": {
            group: rate(sum(1 for run in group_runs if run["passed"]), len(group_runs))
            for group, group_runs in sorted(by_group.items())
        },
        "latency_ms_p50": round(statistics.median(run["duration_ms"] for run in runs), 1) if runs else 0,
        "latency_ms_max": round(max((run["duration_ms"] for run in runs), default=0), 1),
        "generation_input_tokens": generation_input,
        "generation_output_tokens": generation_output,
    }
    if rates:
        cost = generation_input / 1_000_000 * rates["input"] + generation_output / 1_000_000 * rates["output"]
        # Named for what it actually measures. Only the final generation call
        # reports its usage through response metadata; the query planner,
        # evidence selector, candidate narrowing, guardrail, translation and
        # support routing each make their own Bedrock call and none of them are
        # counted here. Real spend is higher, and the planner and selector see
        # the whole candidate set, so the gap is not small.
        summary["measured_generation_cost_usd"] = round(cost, 4)
        summary["generation_cost_per_case_usd"] = round(cost / max(1, len(results)), 4)
        summary["cost_excludes"] = [
            "query_planner", "evidence_selector", "candidate_narrowing",
            "guardrail", "global_translation", "support_routing", "controlled_copy",
        ]
    return summary


def _write_artifact(
    artifact: Path | None,
    summary: dict[str, Any],
    results: list[dict[str, Any]],
) -> None:
    """Atomically preserve a benchmark's completed cases and current state.

    A paid comparison can fail after a response is generated.  Leaving its
    completed cases only in process memory makes the spend and evidence vanish.
    Checkpoints use a sibling temporary file so a stopped process cannot replace
    the last complete record with a partial JSON document.
    """
    if artifact is None:
        return
    artifact.parent.mkdir(parents=True, exist_ok=True)
    temporary = artifact.with_suffix(artifact.suffix + ".tmp")
    temporary.write_text(
        json.dumps({"summary": summary, "cases": results}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(artifact)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument(
        "--transport-overrides",
        type=Path,
        default=None,
        help=(
            "Hash-bound request-country overlay: request_countries for GLOBAL source "
            "cases, abstention_request_countries for cross-market refusal cases."
        ),
    )
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
        transport_overrides, overrides_hash = load_transport_overrides(
            args.transport_overrides, cases, fixture_hash
        )
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
    # A request country the chat API does not accept is found here, for free,
    # rather than by a paid run failing on it. Production preflight blocked on
    # exactly this for held-out case 23, which a dry run reported as valid.
    # Reported, not enforced: other fixtures are not transport-bound.
    unsupported_request_countries = sorted(
        str(case["id"]) for case in cases
        if execution_case_for_request(case, transport_overrides)[1] not in _chat_request_countries()
    )
    if args.dry_run:
        print(json.dumps({
            "status": "valid",
            "cases": len(cases),
            "runs": len(cases) * max(1, args.repeat),
            "generation_calls": model_calls,
            "fixture_sha256": fixture_hash,
            "transport_override_cases": len(transport_overrides),
            "transport_overrides_sha256": overrides_hash,
            "unsupported_request_countries": unsupported_request_countries,
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
    base_summary = {
        "status": "in_progress",
        "planned_cases": len(cases),
        "completed_cases": 0,
        "fixture_sha256": fixture_hash,
        "transport_override_cases": len(transport_overrides),
        "transport_overrides_sha256": overrides_hash,
        "repeat": max(1, args.repeat),
    }
    for index, case in enumerate(cases, start=1):
        request_case, request_country = execution_case_for_request(case, transport_overrides)
        runs = []
        try:
            for attempt in range(max(1, args.repeat)):
                raw = run_case_once(canary, request_case, index * 1000 + attempt)
                runs.append(score_run(case, raw))
        except Exception as exc:  # preserve paid evidence before returning failure
            stopped_summary = {
                **base_summary,
                "status": "stopped",
                "completed_cases": len(results),
                "stopped_case_id": str(case["id"]),
                "error_type": type(exc).__name__,
            }
            _write_artifact(args.artifact, stopped_summary, results)
            print(
                f"benchmark stopped before {case['id']}: {type(exc).__name__}",
                file=sys.stderr,
            )
            return 1
        passed_runs = sum(1 for run in runs if run["passed"])
        results.append({
            "id": case["id"],
            "question": case["question"],
            "source_country": str(case["country"]).upper(),
            "request_country": request_country,
            "evaluation_set": case.get("evaluation_set", "development"),
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
        _write_artifact(
            args.artifact,
            {**base_summary, "completed_cases": len(results)},
            results,
        )

    summary = summarise(results, rates)
    summary.update({
        "index": settings.OPENSEARCH_INDEX,
        "pipeline_version": settings.RETRIEVAL_PIPELINE_VERSION,
        "fixture_sha256": fixture_hash,
        "transport_override_cases": len(transport_overrides),
        "transport_overrides_sha256": overrides_hash,
        "repeat": max(1, args.repeat),
    })
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    if args.artifact:
        _write_artifact(
            args.artifact,
            {
                **summary,
                "status": "completed",
                "planned_cases": len(cases),
                "completed_cases": len(results),
            },
            results,
        )
        print(f"\nfull per-run record written to {args.artifact}", file=sys.stderr)

    # Reporting a measurement is the job; deciding whether it is good enough is
    # not. This never fails a build, unlike the canary.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
