"""Run a cache-free, answer-visible Current versus Candidate evaluation.

This is an evaluation-only entry point. It does not create sessions, write chat
history, read or write answer caches, publish an index, or change the production
retrieval profile. Both sides use the same configured generation model so the
comparison isolates retrieval behavior.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import re
import subprocess
import sys
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_retrieval_canary import (  # noqa: E402
    VNEXT_FACTORS,
    VNEXT_PROFILES,
    _provider_for_profile,
    configure_vnext_experiment,
)

MARKET_ALIASES = {"UK": "GB"}
DOCUMENT_COUNTRY_ALIASES = {"GB": {"GB", "UK"}}
DIRECTORY_HOST_MARKET = "CA"
RETRIEVAL_DEPTHS = (1, 5, 10, 20)
EXPECTED_BEHAVIORS = {"answer", "abstain"}


@dataclass(frozen=True)
class ProfileAnswer:
    """One profile's visible answer and layered evaluation diagnostics."""

    answer: str
    citations: list[dict[str, Any]]
    model_name: str
    answer_status: str
    failure_layer: str
    evidence_approved: bool
    evidence_reason: str
    confidence: float
    candidate_metrics: dict[str, Any]
    selector_success: bool | None
    answer_delivered: bool
    retrieval_repeats: list[dict[str, Any]]


def fixture_sha256(path: Path) -> str:
    """Return the exact source fixture identity."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalized_string_list(
    case: dict[str, Any],
    field: str,
    identifier: str,
) -> list[str]:
    values = case.get(field) or []
    if not isinstance(values, list):
        raise ValueError(f"Case {identifier} {field} must be a list.")
    return [str(value).strip() for value in values if str(value).strip()]


def normalize_fixture(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Normalize source-oriented labels into valid runtime evaluation inputs."""
    from services.market_config import find_market_mentions

    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("The held-out fixture must contain a non-empty cases list.")

    normalized_cases: list[dict[str, Any]] = []
    changes: list[str] = []
    seen: set[str] = set()
    fixture_answer_phrases = payload.get("expected_answer_any") or []
    if not isinstance(fixture_answer_phrases, list):
        raise ValueError("Fixture expected_answer_any must be a list.")
    fixture_answer_phrases = [
        str(value).strip().casefold()
        for value in fixture_answer_phrases
        if str(value).strip()
    ]
    for position, original in enumerate(cases, start=1):
        if not isinstance(original, dict):
            raise ValueError(f"Case {position} must be an object.")
        case = dict(original)
        identifier = str(case.get("id") or "").strip()
        if not identifier or identifier in seen:
            raise ValueError(f"Case IDs must be non-empty and unique: {identifier!r}.")
        seen.add(identifier)
        for required in ("question", "country", "language", "scope", "scoring_rule"):
            if not str(case.get(required) or "").strip():
                raise ValueError(f"Case {identifier} is missing {required}.")

        source_country = str(case["country"]).upper()
        runtime_country = MARKET_ALIASES.get(source_country, source_country)
        case["source_country"] = source_country
        case["country"] = runtime_country
        case["role"] = str(case.get("role") or "new_prospect")
        case["target_country"] = str(case.get("target_country") or "").upper()
        default_behavior = "abstain" if str(case.get("scope") or "") == "out_of_scope" else "answer"
        expected_behavior = str(case.get("expected_behavior") or default_behavior).strip().lower()
        if expected_behavior not in EXPECTED_BEHAVIORS:
            raise ValueError(
                f"Case {identifier} expected_behavior must be one of "
                f"{', '.join(sorted(EXPECTED_BEHAVIORS))}."
            )
        case["expected_behavior"] = expected_behavior
        answer_phrases = case.get("expected_answer_any", fixture_answer_phrases) or []
        if not isinstance(answer_phrases, list):
            raise ValueError(f"Case {identifier} expected_answer_any must be a list.")
        case["expected_answer_any"] = [
            str(value).strip().casefold()
            for value in answer_phrases
            if str(value).strip()
        ]

        if source_country != runtime_country:
            changes.append(f"{identifier}: normalized market {source_country} to {runtime_country}.")
        if str(case.get("scope")) == "global_directory" and runtime_country not in {"CA", "US", "GB", "DE", "IT", "NL"}:
            case["target_country"] = source_country
            case["country"] = DIRECTORY_HOST_MARKET
            changes.append(
                f"{identifier}: preserved {source_country} as the directory target and used "
                f"{DIRECTORY_HOST_MARKET} as the supported widget market."
            )
        elif str(case.get("scope")) == "global_directory" and not case["target_country"]:
            mentioned = find_market_mentions(str(case["question"])) - {runtime_country}
            if len(mentioned) == 1:
                case["target_country"] = next(iter(mentioned))
                changes.append(
                    f"{identifier}: derived directory target {case['target_country']} from the question."
                )

        case["relevant_sections"] = _normalized_string_list(
            case, "relevant_sections", identifier
        )
        case["relevant_section_ids"] = _normalized_string_list(
            case, "relevant_section_ids", identifier
        )
        case["required_source_files"] = _normalized_string_list(
            case, "required_source_files", identifier
        )
        governing = case.get("governing_section")
        case["governing_section"] = str(governing).strip() if governing else None
        normalized_cases.append(case)

    normalized = {
        **payload,
        "normalization": {
            "runtime_market_aliases": MARKET_ALIASES,
            "directory_host_market": DIRECTORY_HOST_MARKET,
            "changes": changes,
        },
        "cases": normalized_cases,
    }
    return normalized, changes


def _section_matches(actual: str, expected: str) -> bool:
    """Match a section or chapter label without allowing 3 to match 13."""
    actual_value = re.sub(r"\s+", "", str(actual or "")).casefold()
    expected_value = re.sub(r"\s+", "", str(expected or "")).casefold()
    if not actual_value or not expected_value:
        return False
    return bool(re.match(rf"^{re.escape(expected_value)}(?:$|[.\-_:/(])", actual_value))


def _allowed_document_countries(country: str) -> set[str]:
    normalized = str(country or "").upper()
    return DOCUMENT_COUNTRY_ALIASES.get(normalized, {normalized})


def _normalized_country_label(value: str) -> str:
    """Normalize country codes and names for directory ground-truth checks."""
    normalized = unicodedata.normalize("NFKD", str(value or "")).casefold()
    return " ".join(
        "".join(character if character.isalnum() else " " for character in normalized).split()
    )


def _directory_target_aliases(country_code: str, relevant_sections: list[str]) -> set[str]:
    """Return data-driven code/name aliases for one directory target country."""
    from services.market_config import load_market_config

    code = str(country_code or "").strip().upper()
    aliases = {_normalized_country_label(code)} if code else set()
    for market in load_market_config().get("markets", []):
        if str(market.get("code") or "").strip().upper() != code:
            continue
        aliases.add(_normalized_country_label(str(market.get("name") or "")))
        aliases.update(
            _normalized_country_label(str(alias))
            for alias in market.get("aliases", [])
            if str(alias).strip()
        )
        break
    for section_id in relevant_sections:
        normalized_section = _normalized_country_label(section_id)
        for prefix in ("sponsoring directory ", "directory "):
            if normalized_section.startswith(prefix):
                aliases.add(normalized_section.removeprefix(prefix).strip())
    return {alias for alias in aliases if alias}


def candidate_is_relevant(candidate: dict[str, Any], case: dict[str, Any]) -> bool:
    """Apply locale-aware section or directory-record ground truth."""
    scope = str(case.get("scope") or "")
    if scope == "out_of_scope" or case.get("expected_behavior") == "abstain":
        return False
    required_sources = {
        str(value).strip().casefold()
        for value in case.get("required_source_files") or []
        if str(value).strip()
    }
    if (
        required_sources
        and str(candidate.get("source_file") or "").strip().casefold()
        not in required_sources
    ):
        return False
    if scope == "global_directory" and case.get("target_country"):
        record_country = _normalized_country_label(str(candidate.get("record_country") or ""))
        return record_country in _directory_target_aliases(
            str(case["target_country"]),
            list(case.get("relevant_sections") or []),
        )

    if str(candidate.get("access_scope") or "country").lower() != "global":
        if str(candidate.get("country") or "").upper() not in _allowed_document_countries(str(case["country"])):
            return False
    actual_section = str(candidate.get("section_id") or "").strip().casefold()
    exact_ids = {
        str(value).strip().casefold()
        for value in case.get("relevant_section_ids") or []
        if str(value).strip()
    }
    if actual_section in exact_ids:
        return True
    relevant_sections = case.get("relevant_sections") or []
    return any(_section_matches(actual_section, section) for section in relevant_sections)


def score_candidates(result: Any, case: dict[str, Any]) -> dict[str, Any]:
    """Compute candidate recall separately from selector and answer delivery."""
    stages = dict((result.metadata or {}).get("candidate_stages") or {})
    candidates = list(stages.get("fused") or [])
    relevant_ranks = [
        index
        for index, candidate in enumerate(candidates, start=1)
        if candidate_is_relevant(candidate, case)
    ]
    first_rank = min(relevant_ranks) if relevant_ranks else None
    return {
        **{f"recall_at_{depth}": bool(first_rank and first_rank <= depth) for depth in RETRIEVAL_DEPTHS},
        "reciprocal_rank": round(1.0 / first_rank, 6) if first_rank else 0.0,
        "first_relevant_rank": first_rank,
        "candidate_count": len(candidates),
        "top_candidates": candidates[:20],
    }


def _selected_is_relevant(result: Any, case: dict[str, Any]) -> bool | None:
    if str(case.get("scope")) == "out_of_scope":
        return None
    selected = list(((result.metadata or {}).get("candidate_stages") or {}).get("selected") or [])
    return any(candidate_is_relevant(candidate, case) for candidate in selected)


def _retrieval_snapshot(result: Any, case: dict[str, Any]) -> dict[str, Any]:
    metrics = score_candidates(result, case)
    return {
        "confidence": round(float(result.confidence or 0.0), 6),
        "document_ids": [document.id for document in result.documents],
        "document_sections": [str(document.metadata.get("section_id") or "") for document in result.documents],
        "selector_success": _selected_is_relevant(result, case),
        "candidate_metrics": metrics,
    }


def _conversation_for_case(
    case: dict[str, Any],
    cases_by_id: dict[str, dict[str, Any]],
    prior_answer: str = "",
) -> tuple[str, str]:
    prior_id = case.get("prior_turn")
    if not prior_id:
        return "", str(case["question"])
    prior = cases_by_id.get(str(prior_id))
    if not prior:
        raise ValueError(f"Case {case['id']} references unknown prior turn {prior_id!r}.")
    if not prior_answer.strip():
        raise ValueError(
            f"Case {case['id']} requires the generated answer from prior turn {prior_id!r}. "
            "Include the prior case in the same evaluation run."
        )
    history = f"User: {prior['question']}\nAssistant: {prior_answer.strip()}"
    return history, str(case["question"])


def _fallback_answer(orchestrator: Any, language: str, correlation_id: str, layer: str) -> Any:
    return orchestrator.response_builder.fallback(
        orchestrator._insufficient_evidence_message(language),
        correlation_id,
        metadata={"failure_layer": layer},
    )


def generate_profile_answer(
    *,
    provider: Any,
    case: dict[str, Any],
    cases_by_id: dict[str, dict[str, Any]],
    profile: str,
    repeats: int,
    generation_model_id: str,
    prior_answer: str = "",
) -> ProfileAnswer:
    """Run cache-free retrieval repeatedly, then generate one visible answer."""
    from app.evidence import approve_evidence, with_approved_evidence
    from app.models.bedrock_provider import BedrockClaudeProvider
    from app.orchestrator.chat_orchestrator import AIOrchestrator
    from utils.validators import ChatRequest

    orchestrator = AIOrchestrator()
    history, user_question = _conversation_for_case(case, cases_by_id, prior_answer)
    correlation_base = f"heldout-{profile}-{case['id']}"
    retrieval_query = orchestrator._build_retrieval_query(user_question, history, correlation_base)
    request_query = orchestrator._build_request_query(user_question, retrieval_query, history)
    body = ChatRequest(
        message=user_question,
        sessionId=correlation_base,
        country=case["country"],
        language=case["language"],
        role=case["role"],
        trafficSource="evaluation",
    )

    governance = orchestrator._evaluate_governance(request_query, body, correlation_base)
    if not governance.allowed:
        response = orchestrator._governance_fallback(
            governance,
            correlation_base,
            body.language,
            body.country,
            body.message,
        )
        return ProfileAnswer(
            answer=response.answer,
            citations=response.citations,
            model_name="governance",
            answer_status="blocked_by_governance",
            failure_layer=str(response.metadata.get("failure_layer") or "governance"),
            evidence_approved=False,
            evidence_reason="governance_blocked",
            confidence=0.0,
            candidate_metrics={f"recall_at_{depth}": False for depth in RETRIEVAL_DEPTHS},
            selector_success=None,
            answer_delivered=False,
            retrieval_repeats=[],
        )

    snapshots: list[dict[str, Any]] = []
    first_result = None
    for repeat in range(1, repeats + 1):
        result = provider.retrieve(
            retrieval_query,
            body.country,
            body.language,
            body.role,
            f"{correlation_base}-retrieval-{repeat}",
        )
        if first_result is None:
            first_result = result
        snapshots.append(_retrieval_snapshot(result, case))
    assert first_result is not None

    decision = approve_evidence(retrieval_query, first_result, body.country, body.language)
    approved_result = with_approved_evidence(first_result, decision)
    metrics = score_candidates(first_result, case)
    selector_success = _selected_is_relevant(first_result, case)
    if not decision.approved:
        response = _fallback_answer(orchestrator, body.language, correlation_base, "evidence_gate")
        return ProfileAnswer(
            answer=response.answer,
            citations=[],
            model_name="fallback",
            answer_status="insufficient_evidence",
            failure_layer="evidence_gate",
            evidence_approved=False,
            evidence_reason=decision.reason,
            confidence=round(float(first_result.confidence or 0.0), 6),
            candidate_metrics=metrics,
            selector_success=selector_success,
            answer_delivered=False,
            retrieval_repeats=snapshots,
        )

    prompt = orchestrator.prompt_builder.build(
        user_question=user_question,
        conversation=history,
        country=body.country,
        language=body.language,
        role=body.role,
        retrieval_result=approved_result,
        metadata={
            "correlation_id": correlation_base,
            "generation_model_id": generation_model_id,
            "evaluation_profile": profile,
            "cache_bypassed": True,
        },
    )
    try:
        model_response = BedrockClaudeProvider().generate(prompt, approved_result, correlation_base)
    except Exception as exc:  # Evaluation must preserve the failure instead of hiding the row.
        response = _fallback_answer(
            orchestrator, body.language, correlation_base, type(exc).__name__
        )
        return ProfileAnswer(
            answer=response.answer,
            citations=[],
            model_name="error",
            answer_status="generation_error",
            failure_layer=type(exc).__name__,
            evidence_approved=True,
            evidence_reason=decision.reason,
            confidence=round(float(first_result.confidence or 0.0), 6),
            candidate_metrics=metrics,
            selector_success=selector_success,
            answer_delivered=False,
            retrieval_repeats=snapshots,
        )
    else:
        if model_response.finish_reason == "guardrail_intervened":
            response = orchestrator.response_builder.fallback(
                "The answer was blocked by the configured Bedrock guardrail.",
                correlation_base,
                metadata={"failure_layer": "aws_guardrail"},
            )
            contracted = None
        else:
            contracted = orchestrator._apply_evidence_contract(model_response, approved_result, correlation_base)
            if contracted is None:
                response = _fallback_answer(orchestrator, body.language, correlation_base, "evidence_contract")

        if contracted is not None:
            model_response, approved_result = contracted
            response = orchestrator.response_builder.build(
                model_response=model_response,
                retrieval_result=approved_result,
                correlation_id=correlation_base,
                session_metadata={"cache": "bypassed", "evaluation_profile": profile},
            )
            response = orchestrator._secure_and_complete_response(
                response,
                approved_result,
                body.language,
                correlation_base,
                user_question=body.message,
                country=body.country,
            )
            response = orchestrator._validate_response(
                response,
                body,
                correlation_base,
                model_response=model_response,
                retrieval_result=approved_result,
            )

    failure_layer = str(response.metadata.get("failure_layer") or "")
    insufficient_answer = orchestrator._insufficient_evidence_message(body.language).strip()
    delivered = bool(
        response.answer.strip()
        and response.answer.strip() != insufficient_answer
        and response.citations
        and not failure_layer
    )
    return ProfileAnswer(
        answer=response.answer,
        citations=response.citations,
        model_name=str(response.metadata.get("model_name") or model_response.model_name),
        answer_status="delivered" if delivered else "fallback_or_blocked",
        failure_layer=failure_layer,
        evidence_approved=True,
        evidence_reason=decision.reason,
        confidence=round(float(first_result.confidence or 0.0), 6),
        candidate_metrics=metrics,
        selector_success=selector_success,
        answer_delivered=delivered,
        retrieval_repeats=snapshots,
    )


def summarize_profile(rows: list[dict[str, Any]], profile: str) -> dict[str, Any]:
    """Summarize only eligible retrieval cases; safety remains a separate gate."""
    def expectation_met(row: dict[str, Any]) -> bool:
        explicit_key = f"{profile}_expectation_met"
        if explicit_key in row:
            return bool(row[explicit_key])
        delivered = bool((row.get(profile) or {}).get("answer_delivered"))
        behavior = str(row.get("expected_behavior") or "answer")
        return not delivered if behavior == "abstain" else delivered

    answers = [row[profile] for row in rows]
    eligible = [
        row[profile]
        for row in rows
        if row["scope"] != "out_of_scope"
        and str(row.get("expected_behavior") or "answer") == "answer"
    ]
    answer_rows = [
        row for row in rows if str(row.get("expected_behavior") or "answer") == "answer"
    ]
    abstain_rows = [
        row for row in rows if str(row.get("expected_behavior") or "answer") == "abstain"
    ]
    summary: dict[str, Any] = {
        "cases": len(answers),
        "retrieval_eligible_cases": len(eligible),
        "answers_delivered": sum(bool(answer["answer_delivered"]) for answer in answers),
        "evidence_approved": sum(bool(answer["evidence_approved"]) for answer in answers),
        "selector_successes": sum(answer["selector_success"] is True for answer in eligible),
        "must_answer_cases": len(answer_rows),
        "must_answer_passes": sum(expectation_met(row) for row in answer_rows),
        "must_abstain_cases": len(abstain_rows),
        "must_abstain_passes": sum(expectation_met(row) for row in abstain_rows),
        "expectation_passes": sum(expectation_met(row) for row in rows),
    }
    for depth in RETRIEVAL_DEPTHS:
        values = [bool(answer["candidate_metrics"].get(f"recall_at_{depth}")) for answer in eligible]
        summary[f"recall_at_{depth}"] = round(sum(values) / len(values), 6) if values else 0.0
    reciprocal_ranks = [float(answer["candidate_metrics"].get("reciprocal_rank") or 0.0) for answer in eligible]
    summary["mrr"] = round(mean(reciprocal_ranks), 6) if reciprocal_ranks else 0.0
    return summary


def profile_meets_expectation(answer: ProfileAnswer, case: dict[str, Any]) -> bool:
    """Apply the fixture's answer-versus-abstain release expectation."""
    if case.get("expected_behavior") == "abstain":
        return not answer.answer_delivered
    expected_answer_any = case.get("expected_answer_any") or []
    normalized_answer = str(answer.answer or "").casefold()
    contains_required_answer = not expected_answer_any or any(
        phrase in normalized_answer for phrase in expected_answer_any
    )
    return bool(
        answer.answer_delivered
        and answer.selector_success is True
        and answer.candidate_metrics.get("recall_at_20")
        and contains_required_answer
    )


def _citation_text(citations: list[dict[str, Any]]) -> str:
    return "; ".join(
        " | ".join(
            part
            for part in (
                str(citation.get("title") or ""),
                str(citation.get("section") or ""),
                str(citation.get("country") or ""),
            )
            if part
        )
        for citation in citations
    )


def write_reports(output_dir: Path, report: dict[str, Any]) -> None:
    """Write machine-readable and human-reviewable side-by-side artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "comparison.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    rows = report["cases"]
    csv_rows: list[dict[str, Any]] = []
    for row in rows:
        csv_rows.append(
            {
                "id": row["id"],
                "category": row["category"],
                "scope": row["scope"],
                "expected_behavior": row["expected_behavior"],
                "country": row["country"],
                "target_country": row.get("target_country", ""),
                "language": row["language"],
                "question": row["question"],
                "current_answer": row["current"]["answer"],
                "candidate_answer": row["candidate"]["answer"],
                "current_citations": _citation_text(row["current"]["citations"]),
                "candidate_citations": _citation_text(row["candidate"]["citations"]),
                "current_recall_at_1": row["current"]["candidate_metrics"].get("recall_at_1"),
                "candidate_recall_at_1": row["candidate"]["candidate_metrics"].get("recall_at_1"),
                "current_first_relevant_rank": row["current"]["candidate_metrics"].get("first_relevant_rank"),
                "candidate_first_relevant_rank": row["candidate"]["candidate_metrics"].get("first_relevant_rank"),
                "current_selector_success": row["current"]["selector_success"],
                "candidate_selector_success": row["candidate"]["selector_success"],
                "current_expectation_met": row["current_expectation_met"],
                "candidate_expectation_met": row["candidate_expectation_met"],
                "human_current_score": "",
                "human_candidate_score": "",
                "reviewer_notes": "",
            }
        )
    with (output_dir / "comparison.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(csv_rows[0]) if csv_rows else [])
        if csv_rows:
            writer.writeheader()
            writer.writerows(csv_rows)

    lines = [
        "# AskVera held-out Current vs Candidate comparison",
        "",
        "> Cache was bypassed. Both profiles used the same generation model. Retrieval, selection, evidence approval, and final answer delivery are reported separately.",
        "",
        "## Summary",
        "",
        f"- Generation model: `{report['manifest']['generation_model_id']}`",
        f"- Current index: `{report['manifest']['current_index']}`",
        f"- Candidate index: `{report['manifest']['candidate_index']}`",
        f"- Retrieval repeats: {report['manifest']['retrieval_repeats']}",
        f"- Current Recall@1: {report['summary']['current']['recall_at_1']:.2%}",
        f"- Candidate Recall@1: {report['summary']['candidate']['recall_at_1']:.2%}",
        f"- Current expectation gate: {report['summary']['current']['expectation_passes']}/{report['summary']['current']['cases']}",
        f"- Candidate expectation gate: {report['summary']['candidate']['expectation_passes']}/{report['summary']['candidate']['cases']}",
        "",
        "## Case-by-case answers",
        "",
    ]
    for row in rows:
        lines.extend(
            [
                f"### {row['id']} - {row['category']}",
                "",
                f"**Question:** {row['question']}",
                "",
                f"**Expected behavior:** {row['expected_behavior']}",
                "",
                f"**Runtime locale:** {row['country']}/{row['language']}" + (f"; target country: {row['target_country']}" if row.get("target_country") else ""),
                "",
                "**Current answer**",
                "",
                row["current"]["answer"],
                "",
                f"Citations: {_citation_text(row['current']['citations']) or 'None'}",
                "",
                f"Recall@1/5/10/20: {row['current']['candidate_metrics'].get('recall_at_1')}/"
                f"{row['current']['candidate_metrics'].get('recall_at_5')}/"
                f"{row['current']['candidate_metrics'].get('recall_at_10')}/"
                f"{row['current']['candidate_metrics'].get('recall_at_20')}; "
                f"selector: {row['current']['selector_success']}; evidence: {row['current']['evidence_approved']}; "
                f"delivered: {row['current']['answer_delivered']}",
                f"; expectation met: {row['current_expectation_met']}",
                "",
                "**Candidate answer**",
                "",
                row["candidate"]["answer"],
                "",
                f"Citations: {_citation_text(row['candidate']['citations']) or 'None'}",
                "",
                f"Recall@1/5/10/20: {row['candidate']['candidate_metrics'].get('recall_at_1')}/"
                f"{row['candidate']['candidate_metrics'].get('recall_at_5')}/"
                f"{row['candidate']['candidate_metrics'].get('recall_at_10')}/"
                f"{row['candidate']['candidate_metrics'].get('recall_at_20')}; "
                f"selector: {row['candidate']['selector_success']}; evidence: {row['candidate']['evidence_approved']}; "
                f"delivered: {row['candidate']['answer_delivered']}",
                f"; expectation met: {row['candidate_expectation_met']}",
                "",
            ]
        )
    (output_dir / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _git_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--load-ssm", action="store_true")
    parser.add_argument("--vnext-index", default="")
    parser.add_argument(
        "--vnext-factor",
        choices=("configured", "none", "parity", *VNEXT_FACTORS, *VNEXT_PROFILES),
        default="configured",
    )
    parser.add_argument("--retrieval-repeats", type=int, default=3)
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--generation-model-id", default="")
    args = parser.parse_args()
    if args.retrieval_repeats < 1:
        parser.error("--retrieval-repeats must be at least 1")

    raw_payload = json.loads(args.fixture.read_text(encoding="utf-8"))
    normalized_fixture, changes = normalize_fixture(raw_payload)
    cases = normalized_fixture["cases"]
    if args.case_id:
        requested = set(args.case_id)
        unknown = requested - {str(case["id"]) for case in cases}
        if unknown:
            parser.error(f"Unknown case IDs: {', '.join(sorted(unknown))}")
        required = set(requested)
        for case in normalized_fixture["cases"]:
            if str(case["id"]) in requested and case.get("prior_turn"):
                required.add(str(case["prior_turn"]))
        cases = [case for case in cases if str(case["id"]) in required]

    from config import settings

    if args.load_ssm:
        settings.load_ssm_config()
    configure_vnext_experiment(index_name=args.vnext_index, factor=args.vnext_factor)
    generation_model_id = args.generation_model_id or settings.BEDROCK_MODEL_ARN
    current_provider = _provider_for_profile("current")
    candidate_provider = _provider_for_profile("vnext")
    cases_by_id = {str(case["id"]): case for case in normalized_fixture["cases"]}
    logging.disable(logging.INFO)

    result_rows: list[dict[str, Any]] = []
    current_answers_by_id: dict[str, str] = {}
    candidate_answers_by_id: dict[str, str] = {}
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] {case['id']}", flush=True)
        current = generate_profile_answer(
            provider=current_provider,
            case=case,
            cases_by_id=cases_by_id,
            profile="current",
            repeats=args.retrieval_repeats,
            generation_model_id=generation_model_id,
            prior_answer=current_answers_by_id.get(str(case.get("prior_turn") or ""), ""),
        )
        candidate = generate_profile_answer(
            provider=candidate_provider,
            case=case,
            cases_by_id=cases_by_id,
            profile="candidate",
            repeats=args.retrieval_repeats,
            generation_model_id=generation_model_id,
            prior_answer=candidate_answers_by_id.get(str(case.get("prior_turn") or ""), ""),
        )
        current_answers_by_id[str(case["id"])] = current.answer
        candidate_answers_by_id[str(case["id"])] = candidate.answer
        result_rows.append(
            {
                "id": case["id"],
                "category": case.get("category", ""),
                "scope": case["scope"],
                "expected_behavior": case["expected_behavior"],
                "country": case["country"],
                "source_country": case.get("source_country", case["country"]),
                "target_country": case.get("target_country", ""),
                "language": case["language"],
                "question": case["question"],
                "relevant_sections": case["relevant_sections"],
                "governing_section": case.get("governing_section"),
                "current": asdict(current),
                "candidate": asdict(candidate),
                "current_expectation_met": profile_meets_expectation(current, case),
                "candidate_expectation_met": profile_meets_expectation(candidate, case),
            }
        )

    manifest = {
        "commit": _git_commit(),
        "source_fixture": str(args.fixture),
        "source_fixture_sha256": fixture_sha256(args.fixture),
        "normalization_changes": changes,
        "cache_bypassed": True,
        "generation_model_id": generation_model_id,
        "current_index": settings.OPENSEARCH_INDEX,
        "candidate_index": settings.OPENSEARCH_VNEXT_INDEX,
        "current_pipeline_version": settings.RETRIEVAL_PIPELINE_VERSION,
        "candidate_pipeline_version": settings.RETRIEVAL_VNEXT_PIPELINE_VERSION,
        "candidate_factor": args.vnext_factor,
        "candidate_factor_state": {name: bool(getattr(settings, setting)) for name, setting in VNEXT_FACTORS.items()},
        "retrieval_repeats": args.retrieval_repeats,
    }
    report = {
        "manifest": manifest,
        "summary": {
            "current": summarize_profile(result_rows, "current"),
            "candidate": summarize_profile(result_rows, "candidate"),
        },
        "cases": result_rows,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "normalized-fixture.json").write_text(
        json.dumps(normalized_fixture, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    write_reports(args.output_dir, report)
    print(json.dumps(report["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
