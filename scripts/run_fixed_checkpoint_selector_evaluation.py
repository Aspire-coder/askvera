"""Measure evidence-selector stability against one frozen retrieval checkpoint.

This evaluation-only tool retrieves each case once with evidence selection
temporarily disabled, preserves the ranked candidate set in memory, and then
replays only the evidence selector against deep copies of that fixed set. It
does not use answer caches, generate customer answers, write chat history,
publish an index, or change production configuration.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import inspect
import json
import logging
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.retrieval.opensearch_sections import _candidate_stage  # noqa: E402
from scripts.run_paraphrase_profile_evaluation import (  # noqa: E402
    VNEXT_FACTORS,
    _provider_for_profile,
    candidate_is_relevant,
    configure_vnext_experiment,
    normalize_fixture,
)


def _approved_retrieval_intents(
    question: str,
    country: str,
    language: str,
) -> list[str]:
    """Use reviewed intents when the runtime provides them, else stay compatible."""
    try:
        from app.retrieval.glossary import approved_retrieval_intents
    except ImportError:
        return []
    return list(approved_retrieval_intents(question, country, language))


def _selector_optional_kwargs(provider: Any, intents: list[str]) -> dict[str, Any]:
    """Pass only optional selector inputs supported by the checked-out runtime."""
    parameters = inspect.signature(provider._select_evidence_rows).parameters
    kwargs: dict[str, Any] = {}
    if "semantic_queries" in parameters:
        kwargs["semantic_queries"] = []
    if "retrieval_intents" in parameters:
        kwargs["retrieval_intents"] = intents
    return kwargs


def fixture_sha256(path: Path) -> str:
    """Return the immutable fixture identity."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def checkpoint_rows_from_result(result: Any) -> list[tuple[dict[str, Any], float]]:
    """Reconstruct selector rows from an expanded, selector-free retrieval."""
    rows: list[tuple[dict[str, Any], float]] = []
    for document in result.documents:
        metadata = dict(document.metadata or {})
        row = {
            "id": document.id,
            "source_file": metadata.get("source_file") or document.title.split(" - ", 1)[0],
            "source_uri": document.source,
            "document_version": document.document_version,
            "document_type": metadata.get("document_type", ""),
            "access_scope": metadata.get("access_scope", "country"),
            "country": document.country,
            "language": document.language,
            "section_id": metadata.get("section_id", ""),
            "section_title": metadata.get("section_title", ""),
            "parent_section_id": metadata.get("parent_section_id", ""),
            "start_page": document.page,
            "end_page": document.page,
            "content": document.content,
            "metadata": metadata,
        }
        rows.append((row, float(document.score or 0.0)))
    return rows


def replay_fixed_selector(
    *,
    provider: Any,
    question: str,
    rows: list[tuple[dict[str, Any], float]],
    country: str,
    language: str,
    case: dict[str, Any],
    repeats: int,
    correlation_base: str,
) -> list[dict[str, Any]]:
    """Replay only the managed selector while keeping candidates unchanged."""
    intents = _approved_retrieval_intents(question, country, language)
    replays: list[dict[str, Any]] = []
    original_selector_state = provider.enable_evidence_selector
    provider.enable_evidence_selector = True
    try:
        for repeat in range(1, repeats + 1):
            replay_rows = copy.deepcopy(rows)
            selected = provider._select_evidence_rows(  # noqa: SLF001 - evaluation-only probe
                question,
                replay_rows,
                f"{correlation_base}-selector-{repeat}",
                **_selector_optional_kwargs(provider, intents),
            )
            diagnostics = replay_rows[0][0] if replay_rows else {}
            selected_stage = _candidate_stage(selected, len(selected))
            replays.append(
                {
                    "repeat": repeat,
                    "decision": str(diagnostics.get("evidence_selector_decision") or ""),
                    "reason": str(diagnostics.get("evidence_selector_reason") or ""),
                    "selected_ranks": list(diagnostics.get("evidence_selector_selected_ranks") or []),
                    "selected_ids": [row["id"] for row in selected_stage],
                    "selected_sections": [row["section_id"] for row in selected_stage],
                    "selected_relevant": any(candidate_is_relevant(row, case) for row in selected_stage),
                }
            )
    finally:
        provider.enable_evidence_selector = original_selector_state
    return replays


def summarize_replays(replays: list[dict[str, Any]]) -> dict[str, Any]:
    """Report selector agreement without conflating it with retrieval recall."""
    signatures = [
        (replay["decision"], tuple(replay["selected_ids"]))
        for replay in replays
    ]
    counts = Counter(signatures)
    dominant = counts.most_common(1)[0][1] if counts else 0
    return {
        "replays": len(replays),
        "unique_outcomes": len(counts),
        "stable": len(counts) <= 1,
        "agreement_rate": round(dominant / len(replays), 6) if replays else 0.0,
        "relevant_selections": sum(replay["selected_relevant"] is True for replay in replays),
        "accepted_relevant_selections": sum(
            replay.get("decision") == "accepted"
            and replay.get("selected_relevant") is True
            for replay in replays
        ),
        "invalid_responses": sum(replay.get("decision") == "invalid" for replay in replays),
        "no_decision_responses": sum(not replay.get("decision") for replay in replays),
        "rejections": sum(replay["decision"].startswith("reject") for replay in replays),
    }


def enrich_saved_report(
    report: dict[str, Any],
    fixture: dict[str, Any],
) -> dict[str, Any]:
    """Recompute layered checkpoint metrics without rerunning retrieval or models."""
    enriched = json.loads(json.dumps(report))
    cases_by_id = {str(case["id"]): case for case in fixture.get("cases") or []}
    for row in enriched.get("cases") or []:
        case = cases_by_id[str(row["id"])]
        for profile in ("current", "candidate"):
            result = row[profile]
            result["checkpoint_relevant"] = any(
                candidate_is_relevant(candidate, case)
                for candidate in result.get("checkpoint") or []
            )
            result["summary"] = summarize_replays(list(result.get("replays") or []))

    aggregate: dict[str, dict[str, Any]] = {}
    for profile in ("current", "candidate"):
        results = [row[profile] for row in enriched.get("cases") or []]
        aggregate[profile] = {
            "cases": len(results),
            "checkpoint_relevant_cases": sum(
                result.get("checkpoint_relevant") is True for result in results
            ),
            "stable_cases": sum(
                result["summary"].get("stable") is True for result in results
            ),
            "all_replays_accepted_relevant": sum(
                result["summary"].get("accepted_relevant_selections")
                == result["summary"].get("replays")
                and result["summary"].get("replays", 0) > 0
                for result in results
            ),
            "any_accepted_relevant": sum(
                result["summary"].get("accepted_relevant_selections", 0) > 0
                for result in results
            ),
            "invalid_responses": sum(
                result["summary"].get("invalid_responses", 0) for result in results
            ),
            "no_decision_responses": sum(
                result["summary"].get("no_decision_responses", 0)
                for result in results
            ),
        }
    enriched["summary"] = aggregate
    return enriched


def _write_report(output_dir: Path, report: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "selector-checkpoint.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Fixed-checkpoint evidence-selector stability",
        "",
        "> Retrieval ran once per case and profile. Only the selector was replayed. Candidate text is intentionally excluded from this artifact.",
        "",
        f"- Commit: `{report['manifest']['commit']}`",
        f"- Fixture SHA-256: `{report['manifest']['fixture_sha256']}`",
        f"- Selector replays: {report['manifest']['selector_replays']}",
        "",
        "## Aggregate",
        "",
        "| Profile | Governing evidence in checkpoint | Stable cases | All replays valid + relevant | Invalid responses |",
        "|---|---:|---:|---:|---:|",
    ]
    for profile in ("current", "candidate"):
        summary = report.get("summary", {}).get(profile, {})
        lines.append(
            f"| {profile} | {summary.get('checkpoint_relevant_cases', 0)}/{summary.get('cases', 0)} | "
            f"{summary.get('stable_cases', 0)}/{summary.get('cases', 0)} | "
            f"{summary.get('all_replays_accepted_relevant', 0)}/{summary.get('cases', 0)} | "
            f"{summary.get('invalid_responses', 0)} |"
        )
    lines.extend(
        [
            "",
            "## Case details",
            "",
            "| Case | Profile | Candidates | Governing evidence | Unique outcomes | Agreement | Valid relevant selections | Invalid |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for case in report["cases"]:
        for profile in ("current", "candidate"):
            result = case[profile]
            summary = result["summary"]
            lines.append(
                f"| {case['id']} | {profile} | {len(result['checkpoint'])} | "
                f"{'yes' if result.get('checkpoint_relevant') else 'no'} | "
                f"{summary['unique_outcomes']} | {summary['agreement_rate']:.0%} | "
                f"{summary['accepted_relevant_selections']}/{summary['replays']} | "
                f"{summary['invalid_responses']} |"
            )
    (output_dir / "selector-checkpoint.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--load-ssm", action="store_true")
    parser.add_argument("--vnext-index", default="")
    parser.add_argument("--vnext-factor", choices=("configured", "none", "parity", *VNEXT_FACTORS), default="parity")
    parser.add_argument("--selector-replays", type=int, default=3)
    parser.add_argument("--candidate-count", type=int, default=20)
    parser.add_argument("--case-id", action="append", default=[])
    args = parser.parse_args()
    if args.selector_replays < 2:
        parser.error("--selector-replays must be at least 2")
    if args.candidate_count < 1:
        parser.error("--candidate-count must be at least 1")

    raw_payload = json.loads(args.fixture.read_text(encoding="utf-8"))
    normalized_fixture, changes = normalize_fixture(raw_payload)
    cases = list(normalized_fixture["cases"])
    if args.case_id:
        requested = set(args.case_id)
        unknown = requested - {str(case["id"]) for case in cases}
        if unknown:
            parser.error(f"Unknown case IDs: {', '.join(sorted(unknown))}")
        cases = [case for case in cases if str(case["id"]) in requested]

    from config import settings

    if args.load_ssm:
        settings.load_ssm_config()
    configure_vnext_experiment(index_name=args.vnext_index, factor=args.vnext_factor)
    providers = {
        "current": _provider_for_profile("current"),
        "candidate": _provider_for_profile("vnext"),
    }
    logging.disable(logging.INFO)

    original_result_count = settings.OPENSEARCH_RESULT_COUNT
    original_min_score = settings.SECTION_RETRIEVAL_MIN_SCORE
    original_selector_states = {
        profile: provider.enable_evidence_selector for profile, provider in providers.items()
    }
    settings.OPENSEARCH_RESULT_COUNT = args.candidate_count
    settings.SECTION_RETRIEVAL_MIN_SCORE = 0.0
    for provider in providers.values():
        provider.enable_evidence_selector = False

    report_cases: list[dict[str, Any]] = []
    try:
        for position, case in enumerate(cases, start=1):
            print(f"[{position}/{len(cases)}] {case['id']}", flush=True)
            row: dict[str, Any] = {
                "id": case["id"],
                "question": case["question"],
                "country": case["country"],
                "language": case["language"],
                "expected_behavior": case["expected_behavior"],
            }
            for profile, provider in providers.items():
                result = provider.retrieve(
                    str(case["question"]),
                    str(case["country"]),
                    str(case["language"]),
                    str(case["role"]),
                    f"fixed-checkpoint-{profile}-{case['id']}-retrieval",
                )
                checkpoint_rows = checkpoint_rows_from_result(result)
                replays = replay_fixed_selector(
                    provider=provider,
                    question=str(case["question"]),
                    rows=checkpoint_rows,
                    country=str(case["country"]),
                    language=str(case["language"]),
                    case=case,
                    repeats=args.selector_replays,
                    correlation_base=f"fixed-checkpoint-{profile}-{case['id']}",
                )
                row[profile] = {
                    "checkpoint": _candidate_stage(checkpoint_rows, len(checkpoint_rows)),
                    "replays": replays,
                    "summary": summarize_replays(replays),
                }
            report_cases.append(row)
    finally:
        settings.OPENSEARCH_RESULT_COUNT = original_result_count
        settings.SECTION_RETRIEVAL_MIN_SCORE = original_min_score
        for profile, provider in providers.items():
            provider.enable_evidence_selector = original_selector_states[profile]

    report = enrich_saved_report({
        "manifest": {
            "commit": _git_commit(),
            "fixture": str(args.fixture),
            "fixture_sha256": fixture_sha256(args.fixture),
            "normalization_changes": changes,
            "cache_bypassed": True,
            "answer_generation": False,
            "retrievals_per_case_profile": 1,
            "selector_replays": args.selector_replays,
            "candidate_count": args.candidate_count,
            "current_index": settings.OPENSEARCH_INDEX,
            "candidate_index": settings.OPENSEARCH_VNEXT_INDEX,
            "candidate_factor": args.vnext_factor,
        },
        "cases": report_cases,
    }, normalized_fixture)
    _write_report(args.output_dir, report)
    print(f"Wrote fixed-checkpoint selector report to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
