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
import ast
import hashlib
import json
import logging
import os
import re
import statistics
import subprocess
import sys
import types
import uuid
from contextlib import contextmanager, suppress
from functools import lru_cache
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterator

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


# Additive disclosure, versioned so a reader can tell a report that has it from
# one that predates it. Scoring never reads any of this.
TRANSPORT_REPORT_VERSION = 1


def _source_market(case: dict[str, Any]) -> str | None:
    source = case.get("source")
    country = str(source.get("country", "")).upper() if isinstance(source, dict) else ""
    return country or None


def transport_record(case: dict[str, Any], transport_overrides: dict[str, str]) -> dict[str, Any]:
    """Say which session a case was declared for and which one it was sent from.

    The legacy per-case ``source_country`` field holds the *declared session*,
    not the source market, so on its own it reads as though case 23 ran in
    Portugal about Portuguese material. This record names both countries and
    the market the expectation is sourced from.

    The mapping is derived rather than stored: ``load_transport_overrides``
    only admits GLOBAL cases through ``request_countries`` and only non-GLOBAL
    cases through ``abstention_request_countries``.
    """
    declared = str(case["country"]).upper()
    _, request_country = execution_case_for_request(case, transport_overrides)
    source_market = _source_market(case)
    transported = request_country != declared
    mapping = None
    if transported:
        mapping = "request_countries" if source_market == "GLOBAL" else "abstention_request_countries"
    return {
        "version": TRANSPORT_REPORT_VERSION,
        "transported": transported,
        "declared_session_country": declared,
        "request_country": request_country,
        "source_market": source_market,
        "mapping": mapping,
    }


def transport_report(cases: list[dict[str, Any]], transport_overrides: dict[str, str]) -> dict[str, Any]:
    """Count coverage by the session a case was actually requested from.

    A transported case still measures its frozen expectation, but it does not
    exercise its declared session. The release validator counts declared
    sessions, which is right for judging a pack's structure and wrong for
    judging what a run covered, so a transported case is never counted toward
    its declared session here. Reported, not enforced.
    """
    records = [(case, transport_record(case, transport_overrides)) for case in cases]
    transported_cases = []
    tags: dict[str, dict[str, int]] = defaultdict(
        lambda: {"declared": 0, "executed_as_declared": 0, "transported": 0}
    )
    new_declared: set[str] = set()
    new_executed: set[str] = set()
    refusals: dict[str, list[str]] = {"declared": [], "executed_as_declared": [], "transported": []}
    for case, record in records:
        coverage = [str(tag) for tag in case.get("coverage") or []]
        state = "transported" if record["transported"] else "executed_as_declared"
        for tag in set(coverage):
            tags[tag]["declared"] += 1
            tags[tag][state] += 1
        if "new_country" in coverage:
            new_declared.add(record["declared_session_country"])
            if not record["transported"]:
                new_executed.add(record["declared_session_country"])
        if "cross_market_refusal" in coverage:
            refusals["declared"].append(str(case["id"]))
            refusals[state].append(str(case["id"]))
        if record["transported"]:
            source_market = record["source_market"]
            transported_cases.append({
                "id": str(case["id"]),
                "declared_session_country": record["declared_session_country"],
                "request_country": record["request_country"],
                "source_market": source_market,
                "mapping": record["mapping"],
                "expected_kind": case["expected"]["kind"],
                "coverage": coverage,
                # Whether the request still asks about another market's local
                # policy. Not applicable to globally scoped directory content.
                "cross_market_after_transport": (
                    None if source_market in (None, "GLOBAL") else record["request_country"] != source_market
                ),
            })
    declared_sessions = {record["declared_session_country"] for _, record in records}
    executed_as_declared = {
        record["declared_session_country"] for _, record in records if not record["transported"]
    }
    return {
        "version": TRANSPORT_REPORT_VERSION,
        "transported_cases": transported_cases,
        "executed_session_countries": sorted({record["request_country"] for _, record in records}),
        "declared_sessions_never_executed": sorted(declared_sessions - executed_as_declared),
        "coverage_as_executed": {
            "new_country_sessions": {
                "declared": sorted(new_declared),
                "executed_as_declared": sorted(new_executed),
                "transported_only": sorted(new_declared - new_executed),
            },
            "cross_market_refusal": refusals,
            "tags": {tag: counts for tag, counts in sorted(tags.items())},
        },
    }


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


# --- Additive run evidence ---------------------------------------------------
#
# A single-sample comparison showed changed decisions it could not explain. It
# recorded the delivered answer, but not the answer repair was handed, what the
# validator found, which evidence was approved, which document a citation
# named, which model answered, or anything about a follow-up's earlier turns.
# Everything below is recorded beside the scored fields. score_run, summarise
# and "passed" never read any of it.

CAPTURE_VERSION = 1
PRESENCE_PIN_VERSION = 1
OUTCOME_CLASSIFICATION_VERSION = 1
RUN_IDENTITY_VERSION = 1
GENERATION_IDENTITY_VERSION = 1

_CAPTURED_RESPONSE_METADATA = frozenset({
    "fallback", "failure_layer", "response_source", "intent", "finish_reason", "provider",
    "model_name", "evidence_decision", "validation", "numeric_claim_repair",
    "removed_numeric_claims", "cache", "retrieval_confidence", "retrieved_document_count",
    "evidence_contract", "mixed_intent", "probable_country", "requested_periods",
    "office_contact_offered", "client_action", "inline_citations_separated",
    "directory_contacts_restored", "directory_role_label_corrected",
    "unrequested_directory_fields_removed", "directory_order_size_restored",
    "directory_source_contradiction_corrected", "response_pii_scrubbed",
    "contact_placeholder_actions", "unresolved_pii_placeholders_removed",
    "empty_after_output_cleanup",
})
_CAPTURED_RETRIEVAL_METADATA = (
    "provider", "candidate_count", "evidence_selector_applied", "evidence_selector_confidence",
    "evidence_selector_rejected", "top_source_directly_answers", "parent_bound_children",
    "conversation_intent", "conversation_subtype", "intent_confidence", "client_action",
    "global_documents_searched", "strong_local_match", "explicit_section_reference",
    "evidence_decision", "generation_lookup",
    "retrieval_rank_lists", "candidate_section_ids", "evidence_selector_candidate_section_ids",
    "evidence_selector_selected_ranks",
)
_CAPTURED_DOCUMENT_METADATA = (
    "section_id", "parent_section_id", "access_scope", "document_type", "parent_bound_child",
    "ingestion_id", "logical_document_id", "content_hash",
)
_CITATION_FIELDS = ("title", "uri", "section", "sectionTitle", "country", "language", "documentVersion", "page", "score")
# Always missing on the current application, whatever the run: the exact key
# that would close each gap is named so it can be added deliberately.
_STATIC_CAPTURE_GAPS = (
    {
        "field": "planner_intent_confidence",
        "reason": "the retrieval planner's intent_confidence is returned only for non-knowledge routes",
        "proposed_metadata_key": "intent_confidence in the knowledge-route RetrievalResult.metadata "
                                 "(app/retrieval/opensearch_sections.py, OpenSearchSectionProvider.retrieve)",
    },
    {
        "field": "candidate_child_section_ids",
        "reason": "candidate_sources is built with RetrievedDocument.to_source(), which reports "
                  "parent_section_id in preference to section_id, so a child candidate reads as its parent",
        "proposed_metadata_key": "candidate_section_ids (each candidate's own section_id, beside candidate_sources)",
    },
    {
        "field": "selector_selected_ranks",
        "reason": "only the documents left after selection and parent-child binding, and the top pick's "
                  "confidence, are exposed; the selector's own selected_ranks list is not",
        "proposed_metadata_key": "evidence_selector_selected_ranks",
    },
)


def _plain(value: Any) -> Any:
    """A JSON-safe copy, so an artifact checkpoint can never fail on a stray type."""
    return json.loads(json.dumps(value, default=str))


@contextmanager
def _orchestrator_diagnostic_capture() -> Iterator[str]:
    """Turn on the orchestrator's diagnostic capture for one pipeline run, then restore it.

    Yields what happened, so an artifact from an application that predates the
    capture says so instead of silently lacking the fields.
    """
    try:
        from app.orchestrator import chat_orchestrator
    except ImportError:
        chat_orchestrator = None
    if chat_orchestrator is None or not hasattr(chat_orchestrator, "DIAGNOSTIC_CAPTURE_ENABLED"):
        yield "orchestrator_unavailable" if chat_orchestrator is None else "unsupported_by_application"
        return
    previous = chat_orchestrator.DIAGNOSTIC_CAPTURE_ENABLED
    chat_orchestrator.DIAGNOSTIC_CAPTURE_ENABLED = True
    try:
        yield "enabled"
    finally:
        chat_orchestrator.DIAGNOSTIC_CAPTURE_ENABLED = previous


def _document_record(document: Any) -> dict[str, Any]:
    metadata = getattr(document, "metadata", None) or {}
    record = {
        "id": str(getattr(document, "id", "") or ""),
        "source": str(getattr(document, "source", "") or ""),
        "country": str(getattr(document, "country", "") or ""),
        "language": str(getattr(document, "language", "") or ""),
        "score": getattr(document, "score", None),
    }
    record.update({key: metadata[key] for key in _CAPTURED_DOCUMENT_METADATA if key in metadata})
    return record


def retrieval_record(retrieval: Any) -> dict[str, Any] | None:
    """One retrieval's documents and selector evidence, without passage text."""
    if retrieval is None:
        return None
    metadata = getattr(retrieval, "metadata", None) or {}
    sources = metadata.get("candidate_sources")
    return _plain({
        "confidence": getattr(retrieval, "confidence", None),
        "documents": [_document_record(document) for document in getattr(retrieval, "documents", None) or []],
        "metadata": {key: metadata[key] for key in _CAPTURED_RETRIEVAL_METADATA if key in metadata},
        # None, not [], when no candidate list is exposed: "not captured" and
        # "no candidates" must not read the same. Each "section" is the
        # parent-preferring to_source() value.
        "candidate_sections": [
            {key: source.get(key) for key in ("section", "country", "uri", "score")}
            for source in sources
            if isinstance(source, dict)
        ] if isinstance(sources, list) else None,
    })


def _question_retrieval(diagnostic: Any) -> dict[str, Any] | None:
    retrievals = diagnostic.get("retrievals") if isinstance(diagnostic, dict) else None
    questions = [item for item in retrievals or [] if isinstance(item, dict) and item.get("stage") == "question"]
    return questions[-1] if questions else None


def turn_record(label: str, response: Any, documents: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """What one turn delivered and, when the application captured it, how it got there."""
    metadata = getattr(response, "metadata", None) or {}
    by_source = {document.get("source"): document for document in documents or [] if document.get("source")}
    citations = []
    for citation in getattr(response, "citations", None) or []:
        if not isinstance(citation, dict):
            continue
        # A citation carries the source URI, which names the document and its
        # own section; the retrieved document gives its id and child section.
        document = by_source.get(citation.get("uri"))
        citations.append({
            **{key: citation[key] for key in _CITATION_FIELDS if key in citation},
            "document_id": document.get("id") if document else None,
            "document_section_id": document.get("section_id") if document else None,
        })
    diagnostic = metadata.get("diagnostic_capture")
    diagnostic = diagnostic if isinstance(diagnostic, dict) else None
    validations = [item for item in (diagnostic or {}).get("validations") or [] if isinstance(item, dict)]
    # The last validation is the one whose outcome was delivered: every return
    # path validates once, and later steps only replace the whole response.
    last = validations[-1] if validations else None
    repair = (last or {}).get("numeric_repair") or {}
    return _plain({
        "turn": label,
        "answer": str(getattr(response, "answer", "") or ""),
        "pre_repair_answer": last.get("answer_before_validation") if last else None,
        "validator_issues": last.get("issues") if last else None,
        "validation_outcome": last.get("outcome") if last else None,
        "removed_claims": repair.get("removal_reasons") or [],
        "citations": citations,
        "metadata": {
            key: value for key, value in metadata.items()
            if key in _CAPTURED_RESPONSE_METADATA or str(key).startswith("model_route_")
        },
        "diagnostic_capture": diagnostic,
    })


def capture_gaps(turns: list[dict[str, Any]], final_retrieval: dict[str, Any] | None, capture_status: str) -> list[dict[str, Any]]:
    """Name every field this run could not record, with the key that would supply it."""
    # Rank-list capture closes these two gaps when the final retrieval carries
    # the key; every other static gap is kept as before.
    supplied = set(((final_retrieval or {}).get("metadata") or {}))
    closed_by = {"candidate_child_section_ids": "candidate_section_ids", "selector_selected_ranks": "evidence_selector_selected_ranks"}
    gaps = [dict(gap) for gap in _STATIC_CAPTURE_GAPS if closed_by.get(gap["field"]) not in supplied]
    without = {
        "pre_repair_answer_validator_findings_and_turn_retrieval": (
            [turn["turn"] for turn in turns if turn["diagnostic_capture"] is None],
            f"no diagnostic_capture on the response (orchestrator capture: {capture_status})",
            "diagnostic_capture",
        ),
        "approved_evidence_ids": (
            [turn["turn"] for turn in turns if not isinstance(turn["metadata"].get("evidence_decision"), dict)],
            "this response path attaches no evidence_decision (conversation route, typo confirmation, "
            "guardrail, cache or period guard)",
            "evidence_decision.evidence_ids",
        ),
        "model_id": (
            [turn["turn"] for turn in turns if not turn["metadata"].get("model_name")],
            "no generation call on this path, or the provider reported no model_name",
            "model_name",
        ),
    }
    for field, (missing_turns, reason, key) in without.items():
        if missing_turns:
            gaps.append({"field": field, "turns": missing_turns, "reason": reason, "proposed_metadata_key": key})
    if final_retrieval is None or final_retrieval.get("candidate_sections") is None:
        gaps.append({
            "field": "selector_candidates",
            "turns": ["final"],
            "reason": "the final retrieval exposed no candidate_sources",
            "proposed_metadata_key": "candidate_sources",
        })
    return gaps


def _summarise_bedrock_usage(records: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Fold one run's captured Bedrock Converse usage records into per-run totals.

    Additive and never scored (part of ``capture``, not a legacy run field).
    ``records`` comes from ``services.aws_clients.capture_bedrock_usage``,
    gated off by default, so this is all zero/empty whenever nothing was
    captured (no real bedrock-runtime client in this process, or capture
    unsupported). Every Bedrock Converse call made through the shared client
    during the run is included, generation call included, so this total is
    not additive with generation_input_tokens/generation_output_tokens
    elsewhere in the run record -- it already contains them.
    """
    records = records or []
    return {
        "input_tokens": sum(int(record.get("input_tokens") or 0) for record in records),
        "output_tokens": sum(int(record.get("output_tokens") or 0) for record in records),
        "call_count": len(records),
        "calls": [dict(record) for record in records],
    }


def capture_record(
    run: Any, capture_status: str = "not_requested", bedrock_usage_records: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Every turn of one run, plus the final retrieval the canary recorded."""
    prior = tuple(getattr(run, "prior_responses", ()) or ())
    final_retrieval = retrieval_record(getattr(run, "retrieval", None))
    labels = [f"turn{number}" for number in range(1, len(prior) + 1)] + ["final"]
    turns = []
    for label, response in zip(labels, [*prior, run.response]):
        turn_retrieval = _question_retrieval((getattr(response, "metadata", None) or {}).get("diagnostic_capture"))
        if turn_retrieval is None and label == "final":
            turn_retrieval = final_retrieval
        turns.append(turn_record(label, response, (turn_retrieval or {}).get("documents")))
    return {
        "version": CAPTURE_VERSION,
        "orchestrator_capture": capture_status,
        "turns": turns,
        "final_retrieval": final_retrieval,
        "generation_snapshot": _generation_snapshot(),
        "gaps": capture_gaps(turns, final_retrieval, capture_status),
        # Additive: see _summarise_bedrock_usage.
        "bedrock_usage": _summarise_bedrock_usage(bedrock_usage_records),
    }


# Snapshot rows by digest, filled as runs happen, so the summary can carry each
# distinct set of publication pointers once instead of once per run.
_GENERATION_SNAPSHOTS: dict[str, list[dict[str, Any]]] = {}


def _generation_snapshot() -> dict[str, Any]:
    """The publication pointers retrieval filtered on, read from the in-process cache only.

    services.knowledge_generations caches the knowledge_active_generations rows
    it loaded for retrieval's ingestion_id filter. Reading that cache costs no
    database query. If the module was never imported or holds nothing, the
    snapshot is reported as not loaded; it is never fetched.
    """
    module = sys.modules.get("services.knowledge_generations")
    rows = getattr(module, "_cache_rows", None) if module is not None else None
    if not isinstance(rows, list) or not rows:
        return {"status": "not_loaded", "sha256": None, "row_count": 0}
    canonical = sorted(json.dumps(row, sort_keys=True, default=str) for row in rows)
    digest = hashlib.sha256("\n".join(canonical).encode("utf-8")).hexdigest()
    _GENERATION_SNAPSHOTS.setdefault(digest, [json.loads(row) for row in canonical])
    return {"status": "in_process_cache", "sha256": digest, "row_count": len(canonical)}


def generation_identity_report(results: list[dict[str, Any]]) -> dict[str, Any]:
    runs_by_snapshot: dict[str, int] = defaultdict(int)
    ingestion_ids: set[str] = set()
    for case in results:
        for run in case["runs"]:
            capture = run.get("capture") or {}
            runs_by_snapshot[(capture.get("generation_snapshot") or {}).get("sha256") or "not_loaded"] += 1
            retrievals = [capture.get("final_retrieval") or {}]
            for turn in capture.get("turns") or []:
                retrievals.extend((turn.get("diagnostic_capture") or {}).get("retrievals") or [])
            ingestion_ids.update(
                str(document["ingestion_id"])
                for retrieval in retrievals
                for document in retrieval.get("documents") or []
                if document.get("ingestion_id")
            )
    return {
        "version": GENERATION_IDENTITY_VERSION,
        "source": "services.knowledge_generations in-process cache, read after each run; the runner makes no database query",
        "runs_by_snapshot": dict(runs_by_snapshot),
        "snapshots": {digest: _GENERATION_SNAPSHOTS[digest] for digest in runs_by_snapshot if digest in _GENERATION_SNAPSHOTS},
        "observed_ingestion_ids": sorted(ingestion_ids),
        "database_snapshot": "not recorded: reading knowledge_active_generations before and after each arm needs "
                             "database access, which this runner does not perform",
    }


# --- One pinned presence function -------------------------------------------
#
# The repair metrics classify each removed figure with numbers_present_in_sources
# from the arm's own validator. When the two arms' validators differ, the same
# removal can be "supported" in one and "invented" in the other, so a delta in
# those metrics is not like-for-like. The legacy fields keep that behaviour
# unchanged; a second, additive classification uses one pinned function whose
# identity is recorded.

_PINNED_PRESENCE: dict[str, Any] = {"function": None, "identity": None}


def _closure_definitions(tree: ast.Module, root: str) -> dict[str, ast.AST]:
    """Module-level definitions ``root`` reaches by name, including through other helpers."""
    definitions: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            definitions[node.name] = node
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                definitions.update({name.id: node for name in ast.walk(target) if isinstance(name, ast.Name)})
    closure: dict[str, ast.AST] = {}
    pending = [root]
    while pending:
        name = pending.pop()
        if name in closure or name not in definitions:
            continue
        closure[name] = definitions[name]
        pending.extend(child.id for child in ast.walk(definitions[name]) if isinstance(child, ast.Name))
    return closure


def presence_function_identity(function: Any) -> dict[str, Any]:
    """Name a function by all the code it runs, not by its own source.

    A hash of the function alone misses behaviour changes made in the helpers
    it calls: a validator revision can leave numbers_present_in_sources and
    remove_unsupported_numeric_sentences byte-identical while rewriting the
    helpers behind them. So two hashes are recorded. ``module_sha256`` is the
    whole validator file and changes on any edit to it. ``closure_sha256``
    covers every module-level definition the function reaches by name,
    transitively, plus the module's import statements, compared as ASTs so
    formatting and line moves do not change it.

    Blind spots of ``closure_sha256``: code in other modules (only the import
    statement is hashed, not app.validation.models or services.market_config
    themselves); behaviour reached through attribute access (re.*, a method
    looked up on an object); names resolved dynamically (getattr, globals());
    configuration and data read at run time; and the interpreter and standard
    library. ``module_sha256`` sees every edit to this file and nothing outside
    it.
    """
    module = sys.modules.get(getattr(function, "__module__", ""))
    path = Path(getattr(module, "__file__", "") or "")
    try:
        raw = path.read_bytes()
        tree = ast.parse(raw)
    except (OSError, SyntaxError, ValueError):
        return {"version": PRESENCE_PIN_VERSION, "status": "source_unavailable", "module_file": str(path)}
    closure = _closure_definitions(tree, function.__name__)
    digest = hashlib.sha256()
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            digest.update(ast.dump(node).encode("utf-8") + b"\n")
    for name in sorted(closure):
        digest.update(name.encode("utf-8") + b"\0" + ast.dump(closure[name]).encode("utf-8") + b"\n")
    try:
        shown = str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        shown = str(path)
    return {
        "version": PRESENCE_PIN_VERSION,
        "status": "recorded",
        "function": function.__name__,
        "module_file": shown.replace("\\", "/"),
        "module_sha256": hashlib.sha256(raw).hexdigest(),
        "closure_names": sorted(closure),
        "closure_sha256": digest.hexdigest(),
    }


def load_presence_function(path: Path) -> Any:
    """Load numbers_present_in_sources from a validator file, such as another revision's."""
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise ValueError(f"Pinned presence validator {path} cannot be read: {exc}") from exc
    name = f"askvera_pinned_presence_{hashlib.sha256(raw).hexdigest()[:16]}"
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        module.__file__ = str(path)
        # Registered before executing: dataclasses resolve their module by name.
        sys.modules[name] = module
        try:
            exec(compile(raw, str(path), "exec"), module.__dict__)
        except Exception as exc:
            sys.modules.pop(name, None)
            raise ValueError(f"Pinned presence validator {path} could not be loaded: {type(exc).__name__}: {exc}") from exc
    function = getattr(module, "numbers_present_in_sources", None)
    if not callable(function):
        raise ValueError(f"Pinned presence validator {path} defines no numbers_present_in_sources.")
    return function


def configure_pinned_presence(path: Path | None) -> None:
    """Pin the presence function for this process; None means the application's own."""
    _PINNED_PRESENCE["function"] = load_presence_function(path) if path is not None else None
    _PINNED_PRESENCE["identity"] = None


def _pinned_presence_function() -> Any:
    if _PINNED_PRESENCE["function"] is None:
        from app.validation.validators.numeric_grounding_validator import numbers_present_in_sources

        _PINNED_PRESENCE["function"] = numbers_present_in_sources
    return _PINNED_PRESENCE["function"]


def pinned_presence_identity() -> dict[str, Any]:
    if _PINNED_PRESENCE["identity"] is None:
        _PINNED_PRESENCE["identity"] = presence_function_identity(_pinned_presence_function())
    return _PINNED_PRESENCE["identity"]


def numeric_repair_identity() -> dict[str, Any]:
    """The application's numeric repair function, identified with all its helpers.

    Not pinned: repair is the behaviour under measurement. Recorded so that two
    arms whose repair differs only inside a helper read as different.
    """
    from app.validation.validators.numeric_grounding_validator import remove_unsupported_numeric_sentences

    return presence_function_identity(remove_unsupported_numeric_sentences)


def _pinned_presence(numbers: list[str], documents: list[Any]) -> dict[str, bool]:
    return _pinned_presence_function()(numbers, documents) if numbers else {}


def _rate(numerator: int, denominator: int) -> str:
    """The same "n/d (p%)" form summarise reports."""
    return f"{numerator}/{denominator}" + (f" ({numerator / denominator:.1%})" if denominator else " (n/a)")


def pinned_repair_report(results: list[dict[str, Any]]) -> dict[str, Any]:
    runs = [
        run for case in results for run in case["runs"]
        if "removed_but_present_in_source_pinned" in run
    ]
    fired = [run for run in runs if run.get("removed_numeric_claims")]
    supported = [run for run in fired if run["removed_but_present_in_source_pinned"]]
    return {
        "version": PRESENCE_PIN_VERSION,
        "presence_function": pinned_presence_identity(),
        "runs_measured": len(runs),
        "repair_fired": _rate(len(fired), len(runs)),
        "repair_removed_supported_figure": _rate(len(supported), len(runs)),
        "repair_removed_invented_figure": _rate(len(fired) - len(supported), len(runs)),
        "note": "Every run classified with the one presence function named here. The legacy "
                "repair_removed_* rates use the application's own function and are unchanged.",
    }


# --- Diagnostic outcome classification ---------------------------------------
#
# "passed" says whether a run met its expectation. It cannot say what the run
# did: a safe "the directory does not state that" reply to a question the
# documents do not answer is scored "answered", exactly like an invented one.
# This labels the delivered behaviour, heuristically, beside "passed", and is
# never read by it.
#
# Limits, stated because they matter:
# * Refusal copy is matched against configured copy only: the locale's
#   reviewed copy, else the English source. It is never translated. (The
#   legacy _abstained, which scoring uses and which is unchanged here, asks
#   Bedrock to translate unreviewed copy.) A live refusal in a locale without
#   reviewed copy is such a translation and will not match; it still counts as
#   declined through the run's own "abstained" flag, but its kind - for
#   example catalogue_scope in Finnish - is not recognised.
# * The cross-market refusal copy exists in English only; in other languages
#   the orchestrator sends the insufficient-evidence copy, which is only
#   recognised as a foreign-policy refusal when the run captured the evidence
#   decision's reason.
# * "safe_not_stated" uses English absence phrases in the first two sentences.
#   A non-English "not stated" reply is classified "answered", and an answer
#   that opens by saying one detail is not stated before giving another is
#   classified "safe_not_stated".

OUTCOMES = ("safe_not_stated", "foreign_policy_refusal", "out_of_scope_refusal", "retrieval_failure", "answered", "other")
_OUT_OF_SCOPE_COPY = ("off_topic", "catalogue_scope", "medical_claim", "income_claim", "period_not_covered")
_FOREIGN_POLICY_REASONS = ("cross_market_policy_request", "cross_market_local_evidence")
_ABSENCE_STATEMENT = re.compile(
    r"\b(?:do|does|did)(?:\s+not|n[’']t)\s+"
    r"(?:have\s+(?:any\s+)?(?:specific\s+)?information|state|specify|mention|say|include|cover|contain|provide|give)\b"
    r"|\bnot\s+(?:stated|specified|mentioned|covered|included)\b"
    r"|\bno\s+(?:specific\s+)?information\b",
    re.IGNORECASE,
)


def _cross_market_scope_copies(language: str) -> list[str]:
    """Every cross-market scope copy the orchestrator can deliver for ``language``.

    The reviewed copy (which names the other market; only the text before its
    {country} placeholder is a stable marker) and the generic English constant,
    which is still delivered when the question names no single other market.
    """
    from app.evidence import configured_conversation_response

    copies = []
    copy, reviewed = configured_conversation_response("cross_market_policy_scope", language)
    if copy and reviewed:
        copies.append(copy.split("{", 1)[0])
    try:
        from app.orchestrator.chat_orchestrator import CROSS_MARKET_POLICY_SCOPE_RESPONSE
    except ImportError:
        return copies
    return [*copies, CROSS_MARKET_POLICY_SCOPE_RESPONSE]


def _configured_copy(key: str, language: str) -> str:
    """The locale's reviewed copy, else the English source. Never a translation.

    localized_conversation_response translates copy that has no reviewed locale
    version with a live Bedrock call. Labelling an outcome must add no model
    call to a benchmark run and make none offline, so it matches only copy that
    exists in configuration.
    """
    from app.evidence import configured_conversation_response

    copy, _reviewed = configured_conversation_response(key, language)
    return copy or ""


def declining_copy_kind(answer: str, language: str) -> str | None:
    """Which configured non-answer copy the delivered text opens with, if any."""
    folded = " ".join((answer or "").split()).casefold()
    if not folded:
        return None
    typo = _configured_copy("country_typo_confirmation", language)
    candidates = [
        *(("cross_market_policy_scope", copy) for copy in _cross_market_scope_copies(language)),
        ("country_typo_confirmation", typo.split("{country}", 1)[0]),
        *((key, _configured_copy(key, language)) for key in _REFUSAL_KEYS),
    ]
    for key, copy in candidates:
        marker = " ".join(copy.split())[:60].casefold()
        if marker and marker in folded:
            return key
    return None


def _evidence_reason(run: dict[str, Any]) -> str:
    turns = (run.get("capture") or {}).get("turns") or []
    decision = (turns[-1].get("metadata") or {}).get("evidence_decision") if turns else None
    return str(decision.get("reason") or "") if isinstance(decision, dict) else ""


def _lead_states_absence(answer: str) -> bool:
    text = " ".join((answer or "").split())
    return bool(_ABSENCE_STATEMENT.search(" ".join(re.split(r"(?<=[.!?])\s+", text)[:2])))


def classify_outcome(run: dict[str, Any], *, language: str, required_sections: list[str] | tuple[str, ...] = ()) -> dict[str, Any]:
    """Label what one run delivered. Automated and heuristic; see the limits above."""
    kind = declining_copy_kind(str(run.get("answer") or ""), language)
    sections = set(run.get("sections") or [])
    declined = kind == "insufficient_evidence" or bool(run.get("abstained"))
    if kind == "country_typo_confirmation":
        outcome, basis = "other", "clarifying_question"
    elif kind == "cross_market_policy_scope" or (declined and _evidence_reason(run) in _FOREIGN_POLICY_REASONS):
        outcome, basis = "foreign_policy_refusal", kind or f"evidence_decision:{_evidence_reason(run)}"
    elif kind in _OUT_OF_SCOPE_COPY:
        outcome, basis = "out_of_scope_refusal", kind
    elif declined and not sections:
        outcome, basis = "retrieval_failure", "declined_with_no_documents_retrieved"
    elif declined and required_sections and not any(section in sections for section in required_sections):
        outcome, basis = "retrieval_failure", "declined_without_the_governing_section_retrieved"
    elif declined:
        outcome, basis = "other", "declined_although_documents_were_retrieved"
    elif _lead_states_absence(str(run.get("answer") or "")):
        outcome, basis = "safe_not_stated", "opening_sentences_say_the_source_does_not_state_it"
    else:
        outcome, basis = "answered", "no_declining_copy_or_absence_statement"
    return {
        "version": OUTCOME_CLASSIFICATION_VERSION,
        "outcome": outcome,
        "basis": basis,
        "declining_copy": kind,
        "method": "automated_heuristic",
    }


def with_diagnostic_outcome(case: dict[str, Any], scored: dict[str, Any]) -> dict[str, Any]:
    required = [str(value) for value in (case["expected"].get("required_sections") or [])]
    return {**scored, "diagnostic_outcome": classify_outcome(scored, language=str(case["language"]), required_sections=required)}


def outcome_report(results: list[dict[str, Any]]) -> dict[str, Any]:
    counts = dict.fromkeys(OUTCOMES, 0)
    by_expected: dict[str, dict[str, int]] = defaultdict(lambda: dict.fromkeys(OUTCOMES, 0))
    runs = 0
    for case in results:
        for run in case["runs"]:
            outcome = (run.get("diagnostic_outcome") or {}).get("outcome")
            if outcome in counts:
                runs += 1
                counts[outcome] += 1
                by_expected[case["expected_kind"]][outcome] += 1
    return {
        "version": OUTCOME_CLASSIFICATION_VERSION,
        "runs": runs,
        "counts": counts,
        "by_expected_kind": dict(by_expected),
        "note": "Automated heuristic classification of delivered behaviour, not manual adjudication. "
                "Never read by passed or any rate. English-only absence phrases under-detect "
                "non-English 'not stated' replies.",
    }


# --- Run identity ---------------------------------------------------------------

_IDENTITY_SETTINGS = (
    "OPENSEARCH_INDEX", "RETRIEVAL_PIPELINE_VERSION", "OPENSEARCH_CANDIDATE_COUNT",
    "OPENSEARCH_RESULT_COUNT", "OPENSEARCH_EVIDENCE_SELECTOR_ENABLED", "OPENSEARCH_RERANK_MODEL_ARN",
    "BEDROCK_MODEL_ARN", "BEDROCK_FALLBACK_MODEL_ARN", "MODEL_ROUTING_MODE", "BEDROCK_FAST_MODEL_ID",
    "BEDROCK_COMPLEX_MODEL_ID", "BEDROCK_EMBED_MODEL_ID", "BEDROCK_REGION", "BEDROCK_MAX_OUTPUT_TOKENS",
    "BEDROCK_GUARDRAIL_ID", "BEDROCK_GUARDRAIL_VERSION", "DEFAULT_MODEL_PROVIDER",
)
_HASHED_UNTRACKED_SUFFIXES = frozenset({".py", ".json", ".jsonl", ".md", ".txt", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".csv"})
_UNHASHED_UNTRACKED_PARTS = (".venv", "venv", "node_modules", "__pycache__", ".git")
_UNTRACKED_HASH_LIMIT_BYTES = 5_000_000
_UNTRACKED_HASH_LIMIT_FILES = 500


def _git(root: Path, *args: str) -> bytes | None:
    try:
        completed = subprocess.run(["git", *args], cwd=root, capture_output=True, check=False, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout if completed.returncode == 0 else None


def _file_sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _hashable_untracked(root: Path, relative: str) -> bool:
    parts = Path(relative).parts
    if any(part.startswith(_UNHASHED_UNTRACKED_PARTS) for part in parts):
        return False
    path = root / relative
    return path.suffix.lower() in _HASHED_UNTRACKED_SUFFIXES and path.is_file() and path.stat().st_size <= _UNTRACKED_HASH_LIMIT_BYTES


def app_revision(root: Path, git: Any = _git) -> dict[str, Any]:
    """Commit, tracked diff hash and untracked source hashes of the tree that ran.

    ``tracked_diff_sha256`` hashes ``git diff HEAD --binary``: staged and
    unstaged changes to tracked files. Untracked source files are hashed
    individually; virtual environments, caches and large or binary files are
    counted but not hashed.
    """
    head = git(root, "rev-parse", "HEAD")
    if head is None:
        return {"status": "unavailable", "reason": "git rev-parse HEAD failed"}
    tracked = git(root, "diff", "HEAD", "--binary") or b""
    status = git(root, "status", "--porcelain=v1", "--untracked-files=all") or b""
    listed = (git(root, "ls-files", "--others", "--exclude-standard", "-z") or b"").decode("utf-8", "replace")
    untracked = sorted(path for path in listed.split("\0") if path)
    hashed = [
        {"path": path, "sha256": _file_sha256(root / path)}
        for path in untracked if _hashable_untracked(root, path)
    ][:_UNTRACKED_HASH_LIMIT_FILES]
    manifest = "\n".join(f"{entry['path']}\0{entry['sha256']}" for entry in hashed)
    return {
        "status": "recorded",
        "commit": head.decode("utf-8", "replace").strip(),
        "dirty": bool(status.strip()),
        "tracked_diff_sha256": hashlib.sha256(tracked).hexdigest(),
        "tracked_diff_bytes": len(tracked),
        "status_sha256": hashlib.sha256(status).hexdigest(),
        "untracked_count": len(untracked),
        "untracked_hashed": hashed,
        "untracked_not_hashed": len(untracked) - len(hashed),
        "untracked_manifest_sha256": hashlib.sha256(manifest.encode("utf-8")).hexdigest(),
    }


def run_identity(settings_module: Any) -> dict[str, Any]:
    """What ran: code revision, runner and canary bytes, model and index settings, presence pin."""
    return _plain({
        "version": RUN_IDENTITY_VERSION,
        "app_revision": app_revision(PROJECT_ROOT),
        "runner_sha256": _file_sha256(Path(__file__)),
        "canary_sha256": _file_sha256(PROJECT_ROOT / "scripts" / "run_retrieval_canary.py"),
        "python": sys.version.split()[0],
        "settings": {name: getattr(settings_module, name, None) for name in _IDENTITY_SETTINGS},
        "presence_function": pinned_presence_identity(),
        "numeric_repair_function": numeric_repair_identity(),
    })


def bedrock_usage_report(results: list[dict[str, Any]], rates: dict[str, float] | None) -> dict[str, Any]:
    """Sum every run's captured Bedrock Converse usage (see capture_record).

    Generation is included in these totals (the accumulator covers every
    Converse call made through the shared client during the run), so this is
    not summed with summarise()'s generation_input_tokens/
    generation_output_tokens -- it already contains them. All zero when
    nothing was captured (no real bedrock-runtime client, or capture
    unsupported in this process).
    """
    usages = [(run.get("capture") or {}).get("bedrock_usage") or {} for case in results for run in case["runs"]]
    input_tokens = sum(int(usage.get("input_tokens") or 0) for usage in usages)
    output_tokens = sum(int(usage.get("output_tokens") or 0) for usage in usages)
    call_count = sum(int(usage.get("call_count") or 0) for usage in usages)
    report = {"input_tokens": input_tokens, "output_tokens": output_tokens, "calls": call_count}
    if rates:
        # A fuller cost figure than summarise()'s measured_generation_cost_usd,
        # which counts only the final generation call: every captured Bedrock
        # Converse call is included here, generation, planner and evidence
        # selector alike. Still not necessarily total spend: a non-Converse
        # Bedrock or AWS service call (e.g. Comprehend PII, Translate,
        # Guardrails) is not captured.
        cost = input_tokens / 1_000_000 * rates["input"] + output_tokens / 1_000_000 * rates["output"]
        report["measured_cost_usd"] = round(cost, 4)
        report["cost_per_case_usd"] = round(cost / max(1, len(results)), 4)
    return report


def diagnostic_summary(
    results: list[dict[str, Any]], identity: dict[str, Any], rates: dict[str, float] | None = None
) -> dict[str, Any]:
    """The additive summary blocks. Never merged over a key summarise() produces."""
    return {
        "run_identity": identity,
        "capture_version": CAPTURE_VERSION,
        "diagnostic_outcomes": outcome_report(results),
        "repair_classification_pinned": pinned_repair_report(results),
        "generation_identity": generation_identity_report(results),
        "bedrock_usage": bedrock_usage_report(results, rates),
    }


def run_case_once(canary, case: dict[str, Any], sequence: int) -> dict[str, Any]:
    """Run one question through the real pipeline and record what came back.

    The run itself is the canary's, deliberately. If the benchmark had its own
    copy of "ask this like a user would", the two could drift -- and the one
    that drifts is always the one nobody runs on every deploy.
    """
    from services.aws_clients import capture_bedrock_usage

    with _orchestrator_diagnostic_capture() as capture_status, capture_bedrock_usage() as bedrock_usage_records:
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
        # Additive and never scored. The same removals, classified with the one
        # pinned presence function recorded in the summary.
        "removed_but_present_in_source_pinned": [
            number
            for number, present in _pinned_presence(run.removed_numeric_claims, documents).items()
            if present
        ],
        "capture": capture_record(run, capture_status, bedrock_usage_records),
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

    The temporary file is named uniquely for each write and created exclusively.
    A fixed ``<artifact>.tmp`` was shared by every run pointed at the same path,
    so one run could write into, or rename away, another run's partial file.
    """
    if artifact is None:
        return
    artifact.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"summary": summary, "cases": results}, indent=2, ensure_ascii=False) + "\n"
    temporary = artifact.with_name(f"{artifact.name}.{uuid.uuid4().hex}.tmp")
    created = False
    try:
        # Text mode, as write_text was, so line endings match earlier artifacts.
        with open(temporary, "x", encoding="utf-8") as handle:
            created = True
            handle.write(payload)
        temporary.replace(artifact)
    except BaseException:
        # Only a file this write created: the name is unique and was opened exclusively.
        if created:
            with suppress(OSError):
                temporary.unlink()
        raise


# Additive disclosure of how a run treated its --artifact path. Scoring never
# reads it.
ARTIFACT_WRITE_VERSION = 1
ARTIFACT_BACKUP_VERSION = 1


def _preserve_replaced_artifact(artifact: Path) -> dict[str, Any]:
    """Copy the file an --overwrite-artifact run is about to replace, and verify the copy.

    Hashing what was replaced says what was lost; it does not keep it. The copy
    is created exclusively beside the artifact as ``<name>.replaced-<sha8>``.
    An existing copy holding the same bytes is reused. One holding different
    bytes is never touched, and the replacement is refused.
    """
    raw = artifact.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    backup = artifact.with_name(f"{artifact.name}.replaced-{digest[:8]}")
    try:
        handle = open(backup, "xb")
    except FileExistsError:
        created = False
    else:
        created = True
        try:
            with handle:
                handle.write(raw)
        except BaseException:
            with suppress(OSError):
                backup.unlink()
            raise
    if hashlib.sha256(backup.read_bytes()).hexdigest() != digest:
        raise FileExistsError(
            f"{backup} exists but does not hold the bytes of {artifact}; refusing to replace the "
            "artifact without a verified copy."
        )
    return {
        "version": ARTIFACT_BACKUP_VERSION,
        "path": str(backup),
        "sha256": digest,
        "bytes": len(raw),
        "created": created,
    }


def _artifact_refusal(artifact: Path) -> str:
    return (
        f"--artifact {artifact} already exists and this run did not create it. "
        "Refusing to replace an existing result artifact; choose a new path, or pass "
        "--overwrite-artifact to replace it deliberately."
    )


def _artifact_write_decision(artifact: Path | None, overwrite: bool) -> dict[str, Any] | None:
    """Decide, before any work, whether this run may write its artifact.

    A frozen baseline was once replaced by a second, failed run pointed at the
    same path. An existing path is refused unless the operator says
    --overwrite-artifact, and even then the replaced bytes are hashed so the
    record says what was lost. ``lexists`` so a dangling link is not mistaken
    for a free path.
    """
    if artifact is None:
        return None
    if not os.path.lexists(artifact):
        return {"version": ARTIFACT_WRITE_VERSION, "mode": "created", "overwrite_flag": overwrite}
    if not overwrite:
        raise FileExistsError(_artifact_refusal(artifact))
    if artifact.is_dir():
        raise IsADirectoryError(f"--artifact {artifact} is a directory, not a result file.")
    raw = artifact.read_bytes()
    return {
        "version": ARTIFACT_WRITE_VERSION,
        "mode": "overwritten",
        "overwrite_flag": True,
        "replaced_sha256": hashlib.sha256(raw).hexdigest(),
        "replaced_bytes": len(raw),
    }


class _ArtifactWriter:
    """One run's --artifact writes: refused over a file this run did not create.

    Constructing it makes the startup decision and raises ``OSError`` on a
    refusal. The startup check cannot see a file another run writes later - the
    overwritten baseline came from a run that had been going for about 45
    minutes - so each write re-checks until this run has written the file once.
    From then on the run owns it, and its checkpoints replace it as before.
    """

    def __init__(self, artifact: Path | None, overwrite: bool) -> None:
        self.artifact = artifact
        self.overwrite = overwrite
        self.decision = _artifact_write_decision(artifact, overwrite)
        self.backup: dict[str, Any] | None = None
        self._owned = False

    def write(self, summary: dict[str, Any], results: list[dict[str, Any]]) -> bool:
        """Write a checkpoint; False, with the reason on stderr, if refused.

        With --overwrite-artifact, the file about to be replaced is first copied
        beside it as ``<name>.replaced-<sha8>``. It is read at the moment of
        replacement, not at startup, so the copy holds exactly the bytes lost.
        The run's own later checkpoints are not copied.
        """
        if self.artifact is None:
            return True
        if not self._owned and os.path.lexists(self.artifact):
            if not self.overwrite:
                print(f"Benchmark artifact refused: {_artifact_refusal(self.artifact)}", file=sys.stderr)
                return False
            try:
                self.backup = _preserve_replaced_artifact(self.artifact)
            except OSError as exc:
                print(f"Benchmark artifact refused: {exc}", file=sys.stderr)
                return False
        if self.backup is not None:
            summary = {**summary, "artifact_backup": self.backup}
        _write_artifact(self.artifact, summary, results)
        self._owned = True
        return True

    def finish(self, summary: dict[str, Any], results: list[dict[str, Any]]) -> int:
        """Write the completed record and return the exit code the run ends with."""
        if not self.write(summary, results):
            return 1
        if self.artifact is not None:
            print(f"\nfull per-run record written to {self.artifact}", file=sys.stderr)
        return 0


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
    parser.add_argument(
        "--case-id", action="append", default=[], dest="case_id",
        help=(
            "Restrict the run to this case id; repeatable for more than one. The full fixture is "
            "always loaded and validated first (including held-out release validation), and "
            "filtering is applied afterwards in this order: --case-id selects cases from the whole "
            "fixture first, then --intent-group narrows that selection, then --limit takes the first "
            "N of what remains. An id not present in the fixture fails closed with a non-zero exit "
            "before any client, SSM or model work and writes no artifact. If --intent-group then "
            "narrows the selected ids down to nothing, the run also fails closed the same way "
            "--limit 0 selecting nothing already does."
        ),
    )
    parser.add_argument("--limit", type=int, default=0, help="Run only the first N cases.")
    parser.add_argument("--intent-group", action="append", default=[], help="Restrict to these groups.")
    parser.add_argument("--repeat", type=int, default=3, help="Runs per case; stochastic stages need a distribution.")
    parser.add_argument("--artifact", type=Path, default=None, help="Write the full per-run record here.")
    parser.add_argument(
        "--overwrite-artifact", action="store_true",
        help=(
            "Allow --artifact to replace a file that already exists. Refused without it. The replaced "
            "file is kept beside it as <name>.replaced-<sha8>."
        ),
    )
    parser.add_argument(
        "--pinned-presence-validator", type=Path, default=None,
        help=(
            "Classify removed figures with numbers_present_in_sources from this validator file, so "
            "two arms are compared under one presence function. Default: the application's own. "
            "Additive only: the legacy repair fields always use the application's own."
        ),
    )
    parser.add_argument(
        "--input-usd-per-million", type=float, default=None,
        help="Your current Bedrock input price. Omit and the report gives tokens only.",
    )
    parser.add_argument("--output-usd-per-million", type=float, default=None)
    args = parser.parse_args()

    # First, before fixture, configuration, SSM or model work: a mistaken
    # invocation over an existing artifact fails fast and costs nothing. Dry
    # runs are checked too, so a preflight of the exact paid command shows it.
    try:
        artifact_writer = _ArtifactWriter(args.artifact, args.overwrite_artifact)
    except OSError as exc:
        print(f"Benchmark artifact refused: {exc}", file=sys.stderr)
        return 2
    return _execute(args, artifact_writer)


def _execute(args: argparse.Namespace, artifact_writer: _ArtifactWriter) -> int:  # noqa: C901
    """Everything after the artifact decision: validate, then dry-run or run the cases."""
    try:
        cases, fixture_hash = load_fixture(args.fixture)
        transport_overrides, overrides_hash = load_transport_overrides(
            args.transport_overrides, cases, fixture_hash
        )
        configure_pinned_presence(args.pinned_presence_validator)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Benchmark fixture is invalid: {exc}", file=sys.stderr)
        return 2

    # Additive: named here once so it lands, unchanged, in the dry-run report
    # and in every summary below. Empty when the flag is absent, so no
    # existing field's value changes.
    requested_case_ids = list(dict.fromkeys(args.case_id))
    if requested_case_ids:
        cases_by_id = {str(case["id"]): case for case in cases}
        unknown_case_ids = [
            identifier for identifier in requested_case_ids if identifier not in cases_by_id
        ]
        if unknown_case_ids:
            print(
                "Unknown --case-id value(s), not present in the loaded fixture: "
                + ", ".join(unknown_case_ids),
                file=sys.stderr,
            )
            return 2
        cases = [cases_by_id[identifier] for identifier in requested_case_ids]
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
    # Over the selected cases, so a --limit or --intent-group run reports what
    # it actually covered.
    transport = transport_report(cases, transport_overrides)
    if args.dry_run:
        report = {
            "status": "valid",
            "cases": len(cases),
            "runs": len(cases) * max(1, args.repeat),
            "generation_calls": model_calls,
            "fixture_sha256": fixture_hash,
            "transport_override_cases": len(transport_overrides),
            "transport_overrides_sha256": overrides_hash,
            "unsupported_request_countries": unsupported_request_countries,
            "transport_report": transport,
            "note": "No model calls were made.",
        }
        # Unconditional: always present, [] when --case-id was not used, so a
        # consumer never has to branch on whether the key exists.
        report["case_ids_requested"] = requested_case_ids
        print(json.dumps(report, indent=2))
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
    # After SSM, so the recorded model and index settings are the ones used.
    identity = run_identity(settings)

    results = []
    base_summary = {
        "status": "in_progress",
        "planned_cases": len(cases),
        "completed_cases": 0,
        "fixture_sha256": fixture_hash,
        "transport_override_cases": len(transport_overrides),
        "transport_overrides_sha256": overrides_hash,
        "transport_report": transport,
        "repeat": max(1, args.repeat),
        "artifact_write": artifact_writer.decision,
        "run_identity": identity,
    }
    # Unconditional: always present, [] when --case-id was not used, so a
    # consumer never has to branch on whether the key exists.
    base_summary["case_ids_requested"] = requested_case_ids
    for index, case in enumerate(cases, start=1):
        request_case, request_country = execution_case_for_request(case, transport_overrides)
        runs = []
        try:
            for attempt in range(max(1, args.repeat)):
                raw = run_case_once(canary, request_case, index * 1000 + attempt)
                runs.append(with_diagnostic_outcome(case, score_run(case, raw)))
        except Exception as exc:  # preserve paid evidence before returning failure
            stopped_summary = {
                **base_summary,
                "status": "stopped",
                "completed_cases": len(results),
                "stopped_case_id": str(case["id"]),
                "error_type": type(exc).__name__,
            }
            artifact_writer.write(stopped_summary, results)
            print(
                f"benchmark stopped before {case['id']}: {type(exc).__name__}",
                file=sys.stderr,
            )
            return 1
        passed_runs = sum(1 for run in runs if run["passed"])
        results.append({
            "id": case["id"],
            "question": case["question"],
            # Legacy name, kept for comparison with earlier artifacts: this is
            # the declared session country, not the source market. The
            # ``transport`` record below names both.
            "source_country": str(case["country"]).upper(),
            "request_country": request_country,
            "transport": transport_record(case, transport_overrides),
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
        if not artifact_writer.write({**base_summary, "completed_cases": len(results)}, results):
            return 1

    summary = summarise(results, rates)
    summary.update({
        "index": settings.OPENSEARCH_INDEX,
        "pipeline_version": settings.RETRIEVAL_PIPELINE_VERSION,
        "fixture_sha256": fixture_hash,
        "transport_override_cases": len(transport_overrides),
        "transport_overrides_sha256": overrides_hash,
        "transport_report": transport,
        "repeat": max(1, args.repeat),
        **diagnostic_summary(results, identity, rates),
    })
    # Unconditional: always present, [] when --case-id was not used, so a
    # consumer never has to branch on whether the key exists.
    summary["case_ids_requested"] = requested_case_ids
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    # Reporting a measurement is the job; deciding whether it is good enough is
    # not. This never fails a build, unlike the canary. The only non-zero exit
    # here is a refusal to replace an artifact this run did not create.
    return artifact_writer.finish(
        {
            **summary,
            "status": "completed",
            "planned_cases": len(cases),
            "completed_cases": len(results),
            "artifact_write": artifact_writer.decision,
        },
        results,
    )


if __name__ == "__main__":
    raise SystemExit(main())
