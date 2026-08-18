"""Inventory and evaluate every historical AskVera interaction.

The default inventory mode is local and side-effect free. Retrieval and answer
evaluation instantiate providers directly, do not use the live retrieval
service, do not write chat analytics, and refuse to run vNext against the
production index. JSONL checkpoints make long Bedrock/OpenSearch runs resumable
without skipping failed rows.
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import logging
import math
import re
import sys
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, replace
from pathlib import Path
from threading import Lock
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.prompts import PromptBuilder  # noqa: E402
from app.retrieval.models import RetrievalResult  # noqa: E402
from app.retrieval.opensearch_sections import OpenSearchSectionProvider  # noqa: E402
from app.retrieval.opensearch_sections import _client as _opensearch_client  # noqa: E402
from app.retrieval.providers import RetrievalQueryPlan  # noqa: E402
from app.retrieval.glossary import glossary_answer_hints  # noqa: E402
from app.retrieval.quality_dataset import (  # noqa: E402
    DatasetIssue,
    InteractionCase,
    dataset_summary,
    parse_interaction_history,
)
from app.retrieval.vnext_quality import (  # noqa: E402
    parse_vnext_evidence_contract,
    vnext_unsupported_numeric_claims,
)
from config import settings  # noqa: E402


EXPECTED_EVIDENCE_FIELDS = (
    "case_id",
    "case_index",
    "country",
    "language",
    "question",
    "expected_source_uris",
    "expected_document_names",
    "expected_document_ids",
    "expected_section_ids",
    "label_status",
    "review_notes",
)

REQUIRED_EXPECTED_EVIDENCE_FIELDS = frozenset(
    {
        "case_id",
        "case_index",
        "country",
        "language",
        "question",
        "expected_document_ids",
        "expected_section_ids",
        "label_status",
        "review_notes",
    }
)

VNEXT_PROFILE_FEATURES: dict[str, frozenset[str]] = {
    "rank-baseline": frozenset(),
    "rank-glossary": frozenset({"glossary"}),
    "rank-glossary-selector": frozenset({"glossary", "evidence_selector"}),
    "rank-glossary-authority": frozenset({"glossary", "authority_ranking"}),
    "rank-rrf": frozenset({"rrf"}),
    "rank-selector": frozenset({"evidence_selector"}),
    "rank-rrf-selector": frozenset({"rrf", "evidence_selector"}),
    "rank-rerank": frozenset({"rerank"}),
    "rank-rerank-authority": frozenset({"rerank", "authority_ranking"}),
    "rank-authority": frozenset({"authority_ranking"}),
    "rank-rrf-authority": frozenset({"rrf", "authority_ranking"}),
    "rank-selector-authority": frozenset(
        {"evidence_selector", "authority_ranking"}
    ),
    "rank-rrf-selector-authority": frozenset(
        {"rrf", "evidence_selector", "authority_ranking"}
    ),
    "index-only": frozenset(),
    "glossary": frozenset({"glossary"}),
    "rrf": frozenset({"rrf"}),
    "parent-diversity": frozenset({"parent_diversity"}),
    "neighbor-expansion": frozenset({"neighbor_expansion"}),
    "evidence-selector": frozenset({"evidence_selector"}),
    "rerank": frozenset({"rerank"}),
    "rrf-selector": frozenset({"rrf", "evidence_selector"}),
    "rrf-selector-quota": frozenset(
        {"rrf", "evidence_selector", "candidate_parent_quota"}
    ),
    "glossary-rrf-selector": frozenset(
        {"glossary", "rrf", "evidence_selector"}
    ),
    "glossary-rrf-selector-rerank": frozenset(
        {"glossary", "rrf", "evidence_selector", "rerank"}
    ),
    "full": frozenset(
        {
            "glossary",
            "rrf",
            "parent_diversity",
            "neighbor_expansion",
            "evidence_selector",
            "rerank",
        }
    ),
}


def _write_expected_evidence_template(
    cases: list[InteractionCase],
    path: Path,
) -> Path:
    """Create a gold-label template without overwriting human review work."""
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=EXPECTED_EVIDENCE_FIELDS)
        writer.writeheader()
        for case in cases:
            writer.writerow(
                {
                    "case_id": case.case_id,
                    "case_index": case.case_index,
                    "country": case.country,
                    "language": case.language,
                    "question": case.question,
                    "expected_source_uris": "",
                    "expected_document_names": "",
                    "expected_document_ids": "",
                    "expected_section_ids": "",
                    "label_status": "needs_review",
                    "review_notes": "",
                }
            )
    return path


def _split_expected_ids(value: str) -> tuple[str, ...]:
    """Parse human-entered comma, semicolon, pipe, or newline separated IDs."""
    values: list[str] = []
    for item in re.split(r"[,;|\n]+", value or ""):
        cleaned = item.strip()
        if cleaned and cleaned not in values:
            values.append(cleaned)
    return tuple(values)


def _load_expected_evidence_labels(path: Path) -> dict[str, dict[str, Any]]:
    """Load only approved expected-evidence labels keyed by immutable case ID."""
    if not path.exists():
        return {}
    labels: dict[str, dict[str, Any]] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_EXPECTED_EVIDENCE_FIELDS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                "Expected-evidence label file is missing columns: "
                + ", ".join(sorted(missing))
            )
        for row_number, row in enumerate(reader, start=2):
            case_id = str(row.get("case_id") or "").strip()
            if not case_id:
                raise ValueError(f"Expected-evidence row {row_number} has no case_id.")
            if case_id in labels:
                raise ValueError(f"Duplicate expected-evidence case_id: {case_id}")
            status = str(row.get("label_status") or "").strip().lower()
            if status != "approved":
                continue
            document_ids = _split_expected_ids(str(row.get("expected_document_ids") or ""))
            section_ids = _split_expected_ids(str(row.get("expected_section_ids") or ""))
            source_uris = _split_expected_ids(str(row.get("expected_source_uris") or ""))
            document_names = _split_expected_ids(
                str(row.get("expected_document_names") or "")
            )
            if not source_uris and not document_names and not document_ids and not section_ids:
                raise ValueError(
                    f"Approved expected-evidence row {row_number} has no source, document, or section IDs."
                )
            labels[case_id] = {
                "expected_source_uris": list(source_uris),
                "expected_document_names": list(document_names),
                "expected_document_ids": list(document_ids),
                "expected_section_ids": list(section_ids),
                "label_status": status,
                "review_notes": str(row.get("review_notes") or "").strip(),
            }
    return labels


def _apply_expected_evidence_labels(
    rows: list[dict[str, Any]],
    labels: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach labels after checkpoint loading so reviews need no reretrieval."""
    labeled_rows: list[dict[str, Any]] = []
    for row in rows:
        labeled = dict(row)
        label = labels.get(str(row.get("case_id") or ""))
        if label:
            labeled["expected_evidence"] = label
        labeled_rows.append(labeled)
    return labeled_rows


def _write_inventory(
    cases: list[InteractionCase],
    issues: list[DatasetIssue],
    output_dir: Path,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    inventory_jsonl = output_dir / "interaction_inventory.jsonl"
    inventory_csv = output_dir / "interaction_inventory.csv"
    review_csv = output_dir / "interaction_review_queue.csv"
    issues_json = output_dir / "interaction_parse_issues.json"
    summary_json = output_dir / "interaction_inventory_summary.json"

    inventory_jsonl.write_text(
        "".join(json.dumps(case.to_dict(), ensure_ascii=False) + "\n" for case in cases),
        encoding="utf-8",
    )
    with inventory_csv.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(cases[0].to_dict()) if cases else [])
        if cases:
            writer.writeheader()
            writer.writerows(case.to_dict() for case in cases)

    review_fields = [
        "case_index",
        "case_id",
        "country",
        "language",
        "question",
        "rating",
        "historical_answer",
        "reviewer_comment",
        "expected_answer",
        "review_state",
        "expected_source_ids",
        "must_include_facts",
        "must_not_include_facts",
        "final_review_status",
        "review_notes",
    ]
    with review_csv.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=review_fields)
        writer.writeheader()
        for case in cases:
            if case.rating is None and not case.has_review_guidance:
                continue
            writer.writerow(
                {
                    "case_index": case.case_index,
                    "case_id": case.case_id,
                    "country": case.country,
                    "language": case.language,
                    "question": case.question,
                    "rating": case.rating,
                    "historical_answer": case.historical_answer,
                    "reviewer_comment": case.reviewer_comment,
                    "expected_answer": case.expected_answer,
                    "review_state": case.review_state,
                    "expected_source_ids": "",
                    "must_include_facts": "",
                    "must_not_include_facts": "",
                    "final_review_status": "",
                    "review_notes": "",
                }
            )

    issues_json.write_text(
        json.dumps([asdict(issue) for issue in issues], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    summary_json.write_text(
        json.dumps(dataset_summary(cases, issues), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return {
        "inventory_jsonl": inventory_jsonl,
        "inventory_csv": inventory_csv,
        "review_csv": review_csv,
        "issues_json": issues_json,
        "summary_json": summary_json,
    }


def _provider_snapshot(result: RetrievalResult) -> dict[str, Any]:
    return {
        "status": "RESULT" if result.documents else "NO_RESULT",
        "confidence": round(float(result.confidence or 0.0), 4),
        "source_count": len(result.documents),
        "candidate_count": int(result.metadata.get("candidate_count", 0) or 0),
        "conversation_intent": str(result.metadata.get("conversation_intent") or ""),
        "documents": [
            {
                "rank": rank,
                "id": document.id,
                "title": document.title,
                "source": document.source,
                "page": document.page,
                "score": document.score,
                "section": document.metadata.get("parent_section_id")
                or document.metadata.get("section_id")
                or "",
                "excerpt": (document.excerpt or document.content or "")[:500],
            }
            for rank, document in enumerate(result.documents, start=1)
        ],
        "metadata": {
            key: result.metadata.get(key)
            for key in (
                "provider",
                "search_query_count",
                "global_documents_searched",
                "explicit_section_reference",
                "experimental_features",
                "rrf_enabled",
                "parent_diversity_enabled",
                "neighbor_expansion_enabled",
            )
            if key in result.metadata
        },
        "candidate_evidence": list(result.metadata.get("candidate_evidence") or []),
    }


def _error_snapshot(exc: BaseException) -> dict[str, Any]:
    return {
        "status": "ERROR",
        "error_type": type(exc).__name__,
        "error": str(exc)[:2000],
        "confidence": 0.0,
        "source_count": 0,
        "candidate_count": 0,
        "documents": [],
    }


def _configure_vnext_profile(profile: str) -> frozenset[str]:
    """Reset and enable exactly one reproducible evaluator feature profile."""
    try:
        features = VNEXT_PROFILE_FEATURES[profile]
    except KeyError as exc:
        raise ValueError(f"Unknown vNext profile: {profile}") from exc
    settings.RETRIEVAL_VNEXT_GLOSSARY_ENABLED = "glossary" in features
    settings.RETRIEVAL_VNEXT_EVIDENCE_SELECTOR_ENABLED = "evidence_selector" in features
    settings.RETRIEVAL_VNEXT_RRF_ENABLED = "rrf" in features
    settings.RETRIEVAL_VNEXT_PARENT_DIVERSITY_ENABLED = "parent_diversity" in features
    settings.RETRIEVAL_VNEXT_CANDIDATE_PARENT_QUOTA_ENABLED = (
        "candidate_parent_quota" in features
    )
    settings.RETRIEVAL_VNEXT_NEIGHBOR_EXPANSION_ENABLED = "neighbor_expansion" in features
    # An explicitly selected evaluator profile is itself authorization to run
    # the isolated experiment. It must not depend on the production shadow
    # toggle, which remains disabled unless a separately reviewed deployment
    # enables it.
    settings.RETRIEVAL_VNEXT_RERANK_ENABLED = "rerank" in features
    return features


class _SharedEvaluationPlanCache:
    """Build one immutable query plan per case for paired rank ablations."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._plans: dict[tuple[str, ...], Future[RetrievalQueryPlan]] = {}

    def get_or_build(
        self,
        key: tuple[str, ...],
        builder: Any,
    ) -> RetrievalQueryPlan:
        with self._lock:
            future = self._plans.get(key)
            owner = future is None
            if future is None:
                future = Future()
                self._plans[key] = future
        if owner:
            try:
                future.set_result(builder())
            except BaseException as exc:
                future.set_exception(exc)
                raise
        return future.result()


class _SharedEvaluationTranslationCache:
    """Build one global-document translation per message and language."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._values: dict[tuple[str, str], Future[str]] = {}

    def get_or_build(self, key: tuple[str, str], builder: Any) -> str:
        with self._lock:
            future = self._values.get(key)
            owner = future is None
            if future is None:
                future = Future()
                self._values[key] = future
        if owner:
            try:
                future.set_result(builder())
            except BaseException as exc:
                future.set_exception(exc)
                raise
        return future.result()


class _SharedEvaluationSearchCache:
    """Execute each identical OpenSearch request once for paired rank ablations."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self._lock = Lock()
        self._responses: dict[str, Future[dict[str, Any]]] = {}

    def search(self, *, index: str, body: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        key = json.dumps(
            {"index": index, "body": body, "kwargs": kwargs},
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        with self._lock:
            future = self._responses.get(key)
            owner = future is None
            if future is None:
                future = Future()
                self._responses[key] = future
        if owner:
            try:
                future.set_result(self._client.search(index=index, body=body, **kwargs))
            except BaseException as exc:
                future.set_exception(exc)
                raise
        return copy.deepcopy(future.result())


class _EvaluationOpenSearchProvider(OpenSearchSectionProvider):
    """Use a shared planner result while leaving retrieval/ranking independent."""

    def __init__(
        self,
        *args: Any,
        plan_cache: _SharedEvaluationPlanCache,
        translation_cache: _SharedEvaluationTranslationCache | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._plan_cache = plan_cache
        self._translation_cache = translation_cache

    def _build_search_plan(
        self,
        message: str,
        country: str,
        language: str,
        correlation_id: str,
    ) -> RetrievalQueryPlan:
        # Pairing is valid only when planner-affecting controls match. In
        # particular, glossary-only ablations intentionally use different
        # planner inputs on the two sides.
        key = (message, country, language, str(self.glossary_enabled))
        return self._plan_cache.get_or_build(
            key,
            lambda: super(_EvaluationOpenSearchProvider, self)._build_search_plan(
                message,
                country,
                language,
                correlation_id,
            ),
        )

    def _global_search_query(
        self,
        message: str,
        language: str,
        correlation_id: str,
    ) -> str:
        if self._translation_cache is None:
            return super()._global_search_query(message, language, correlation_id)
        return self._translation_cache.get_or_build(
            (message, language),
            lambda: super(_EvaluationOpenSearchProvider, self)._global_search_query(
                message,
                language,
                correlation_id,
            ),
        )


def _vnext_provider(
    profile: str,
    index_name: str | None = None,
    plan_cache: _SharedEvaluationPlanCache | None = None,
    *,
    allow_same_index_rank_ablation: bool = False,
    search_client: Any | None = None,
    translation_cache: _SharedEvaluationTranslationCache | None = None,
) -> OpenSearchSectionProvider:
    selected_index = str(index_name or settings.OPENSEARCH_VNEXT_INDEX).strip()
    if not selected_index:
        raise RuntimeError("OPENSEARCH_VNEXT_INDEX is required for isolated vNext evaluation.")
    same_index = selected_index == settings.OPENSEARCH_INDEX
    if same_index and not (
        allow_same_index_rank_ablation and profile.startswith("rank-")
    ):
        raise RuntimeError("vNext evaluation refused: OPENSEARCH_VNEXT_INDEX matches OPENSEARCH_INDEX.")
    features = _configure_vnext_profile(profile)
    controlled_rank_profile = profile.startswith("rank-")
    if "rerank" in features and not (
        settings.RETRIEVAL_VNEXT_RERANK_ENABLED
        and settings.RETRIEVAL_VNEXT_RERANK_MODEL_ARN
    ):
        raise RuntimeError(
            "The rerank profile requires RETRIEVAL_VNEXT_RERANK_ENABLED and "
            "RETRIEVAL_VNEXT_RERANK_MODEL_ARN."
        )
    rerank_enabled = bool(
        "rerank" in features
        and settings.RETRIEVAL_VNEXT_RERANK_ENABLED
        and settings.RETRIEVAL_VNEXT_RERANK_MODEL_ARN
    )
    provider_type = (
        _EvaluationOpenSearchProvider if plan_cache is not None else OpenSearchSectionProvider
    )
    provider_kwargs: dict[str, Any] = {}
    if plan_cache is not None:
        provider_kwargs["plan_cache"] = plan_cache
        provider_kwargs["translation_cache"] = translation_cache
    return provider_type(
        index_name=selected_index,
        search_client=search_client,
        enable_bedrock_rerank=rerank_enabled,
        experimental_features=(
            bool(features) if controlled_rank_profile else True
        ),
        result_count=(
            settings.OPENSEARCH_RESULT_COUNT
            if controlled_rank_profile
            else settings.RETRIEVAL_VNEXT_RESULT_COUNT
        ),
        glossary_enabled=(
            (
                "glossary" in features
                if controlled_rank_profile
                else "glossary" in features
            )
        ),
        evidence_selector_enabled=(
            (
                True
                if "evidence_selector" in features
                else False
            )
            if controlled_rank_profile
            else "evidence_selector" in features
        ),
        authority_ranking_enabled="authority_ranking" in features,
        **provider_kwargs,
    )


def _generate_answer(case: InteractionCase, retrieval_result: RetrievalResult) -> dict[str, Any]:
    # Keep inventory and retrieval-only runs independent from model setup.
    from app.models.router import model_router

    if not retrieval_result.documents:
        intent = str(retrieval_result.metadata.get("conversation_intent") or "")
        return {
            "status": f"ROUTED_{intent.upper()}" if intent and intent != "knowledge" else "NO_EVIDENCE",
            "answer": "",
            "evidence_ids": [],
            "unsupported_numeric_claims": [],
        }

    settings.EVIDENCE_GATED_OUTPUT_ENABLED = True
    package = PromptBuilder().build(
        user_question=case.question,
        conversation="",
        country=case.country,
        language=case.language,
        role="new_prospect",
        retrieval_result=retrieval_result,
        metadata={"correlation_id": f"quality-eval-{case.case_id}"},
    )
    hints = glossary_answer_hints(
        case.question,
        case.country,
        case.language,
        enabled=settings.RETRIEVAL_VNEXT_GLOSSARY_ENABLED,
    )
    if hints:
        package = replace(
            package,
            system_prompt=(
                package.system_prompt
                + "\n\nReviewed terminology hints (use only with supporting retrieved evidence):\n- "
                + "\n- ".join(hints)
            ),
        )
    try:
        contract = None
        model_response = None
        attempts = 0
        for attempts in range(1, 3):
            model_response = model_router.generate(
                package,
                retrieval_result,
                f"quality-eval-{case.case_id}-attempt-{attempts}",
            )
            contract = parse_vnext_evidence_contract(
                model_response.text,
                retrieval_result.documents,
            )
            if contract.valid or contract.reason == "answer_not_approved":
                break
            if attempts == 1:
                package = replace(
                    package,
                    system_prompt=(
                        package.system_prompt
                        + "\n\nYour previous response failed the JSON evidence contract. Regenerate once. "
                        "Return one valid JSON object, escape every quote inside string values, and ensure "
                        "top-level evidence_ids contains every ID used by claims. If evidence is insufficient, "
                        "use status insufficient_evidence with an empty answer and no claims."
                    ),
                )
        assert model_response is not None and contract is not None
        if not contract.valid:
            status = (
                "SAFE_ABSTENTION"
                if contract.reason == "answer_not_approved"
                else "EVIDENCE_CONTRACT_REJECTED"
            )
            return {
                "status": status,
                "answer": "",
                "evidence_ids": [],
                "unsupported_numeric_claims": [],
                "error": contract.reason,
                "raw_response": model_response.text[:20000],
                "contract_attempts": attempts,
            }
        unsupported = vnext_unsupported_numeric_claims(
            contract.answer,
            case.question,
            retrieval_result.documents,
            contract.evidence_ids,
        )
        return {
            "status": "APPROVED" if not unsupported else "NUMERIC_REVIEW_REQUIRED",
            "answer": contract.answer,
            "evidence_ids": list(contract.evidence_ids),
            "unsupported_numeric_claims": [claim.text for claim in unsupported],
            "token_usage": model_response.token_usage,
            "model": model_response.model_name,
            "raw_response": model_response.text[:20000],
            "contract_attempts": attempts,
        }
    except Exception as exc:  # noqa: BLE001 - retain one result for every input row.
        return {
            "status": "ERROR",
            "answer": "",
            "evidence_ids": [],
            "unsupported_numeric_claims": [],
            "error_type": type(exc).__name__,
            "error": str(exc)[:2000],
        }


def _load_completed(path: Path) -> dict[str, dict[str, Any]]:
    completed: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return completed
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        completed[str(row["case_id"])] = row
    return completed


def _has_error(row: dict[str, Any]) -> bool:
    return any(
        isinstance(value, dict) and value.get("status") == "ERROR"
        for key, value in row.items()
        if key
        in {
            "current_retrieval",
            "current_answer",
            "vnext_retrieval",
            "vnext_answer",
        }
    )


def _should_retry(row: dict[str, Any], args: argparse.Namespace) -> bool:
    if args.retry_errors and _has_error(row):
        return True
    if args.generate_answers:
        if args.pipeline in {"current", "both"} and not isinstance(
            row.get("current_answer"),
            dict,
        ):
            return True
        if args.pipeline in {"vnext", "both"} and not isinstance(
            row.get("vnext_answer"),
            dict,
        ):
            return True
    retry_statuses = set(args.retry_answer_status)
    return any(
        str((row.get(key) or {}).get("status") or "") in retry_statuses
        for key in ("current_answer", "vnext_answer")
    )


def _evaluate_case(
    args: argparse.Namespace,
    case: InteractionCase,
    current_provider: OpenSearchSectionProvider | None,
    vnext_provider: OpenSearchSectionProvider | None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "case_index": case.case_index,
        "case_id": case.case_id,
        "country": case.country,
        "language": case.language,
        "question": case.question,
        "rating": case.rating,
        "reviewer_comment": case.reviewer_comment,
        "expected_answer": case.expected_answer,
        "evaluation_group": case.evaluation_group,
        "vnext_profile": args.vnext_profile if args.pipeline in {"vnext", "both"} else "",
    }
    if current_provider:
        try:
            started = time.perf_counter()
            current = current_provider.retrieve(
                case.question,
                case.country,
                case.language,
                "new_prospect",
                f"history-current-{case.case_id}",
            )
            row["current_retrieval"] = _provider_snapshot(current)
            row["current_retrieval"]["latency_ms"] = round(
                (time.perf_counter() - started) * 1000,
                2,
            )
            if args.generate_answers:
                row["current_answer"] = _generate_answer(case, current)
        except Exception as exc:  # noqa: BLE001
            row["current_retrieval"] = _error_snapshot(exc)
            if args.generate_answers:
                row["current_answer"] = _error_snapshot(exc)
    if vnext_provider:
        try:
            started = time.perf_counter()
            vnext = vnext_provider.retrieve(
                case.question,
                case.country,
                case.language,
                "new_prospect",
                f"history-vnext-{case.case_id}",
            )
            row["vnext_retrieval"] = _provider_snapshot(vnext)
            row["vnext_retrieval"]["latency_ms"] = round(
                (time.perf_counter() - started) * 1000,
                2,
            )
            if args.generate_answers:
                row["vnext_answer"] = _generate_answer(case, vnext)
        except Exception as exc:  # noqa: BLE001
            row["vnext_retrieval"] = _error_snapshot(exc)
            if args.generate_answers:
                row["vnext_answer"] = _error_snapshot(exc)
    if args.sleep_ms > 0:
        time.sleep(args.sleep_ms / 1000)
    return row


def _evaluate_cases(args: argparse.Namespace, cases: list[InteractionCase]) -> tuple[Path, list[dict[str, Any]]]:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = args.output_dir / f"{args.run_name}.jsonl"
    completed = _load_completed(checkpoint) if args.resume else {}
    if not args.resume:
        checkpoint.write_text("", encoding="utf-8")
    plan_cache = _SharedEvaluationPlanCache() if args.pipeline == "both" else None
    translation_cache = (
        _SharedEvaluationTranslationCache() if args.pipeline == "both" else None
    )
    search_cache = (
        _SharedEvaluationSearchCache(_opensearch_client())
        if args.allow_same_index_rank_ablation
        else None
    )
    current_provider = (
        _EvaluationOpenSearchProvider(
            plan_cache=plan_cache,
            translation_cache=translation_cache,
            search_client=search_cache,
            evidence_selector_enabled=(
                (
                    bool(args.rank_ablation_current_selector)
                    if args.allow_same_index_rank_ablation
                    else None
                )
            ),
            glossary_enabled=(
                False
                if args.rank_ablation_disable_current_glossary
                else None
            ),
        )
        if plan_cache is not None
        else OpenSearchSectionProvider()
    ) if args.pipeline in {"current", "both"} else None
    vnext_provider = (
        _vnext_provider(
            args.vnext_profile,
            args.vnext_index,
            plan_cache,
            allow_same_index_rank_ablation=args.allow_same_index_rank_ablation,
            search_client=search_cache,
            translation_cache=translation_cache,
        )
        if args.pipeline in {"vnext", "both"}
        else None
    )

    selected = [case for case in cases if case.case_index >= args.start_at]
    if args.rated_only:
        selected = [case for case in selected if case.rating is not None]
    if args.max_cases > 0:
        selected = selected[: args.max_cases]

    pending = [
        case
        for case in selected
        if not completed.get(case.case_id)
        or _should_retry(completed[case.case_id], args)
    ]
    worker_count = max(1, min(int(args.workers), 4))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        results = executor.map(
            lambda case: _evaluate_case(args, case, current_provider, vnext_provider),
            pending,
        )
        for position, (case, row) in enumerate(zip(pending, results, strict=True), start=1):
            completed[case.case_id] = row
            with checkpoint.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"[{position}/{len(pending)}] case {case.case_index}: {case.question[:100]}")
    ordered = sorted(completed.values(), key=lambda value: value["case_index"])
    labels = _load_expected_evidence_labels(args.expected_evidence_labels)
    ordered = _apply_expected_evidence_labels(ordered, labels)
    return checkpoint, ordered


def _result_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {"evaluated_cases": len(rows)}
    for key in (
        "current_retrieval",
        "current_answer",
        "vnext_retrieval",
        "vnext_answer",
    ):
        statuses: dict[str, int] = {}
        applicable = [row[key] for row in rows if isinstance(row.get(key), dict)]
        for value in applicable:
            status = str(value.get("status") or "UNKNOWN")
            statuses[status] = statuses.get(status, 0) + 1
        summary[key] = {
            "count": len(applicable),
            "statuses": dict(sorted(statuses.items())),
            "document_result_rate_all_interactions": round(
                sum(value.get("status") == "RESULT" for value in applicable) / max(1, len(applicable)),
                4,
            )
            if key.endswith("retrieval")
            else None,
            "approved_rate": round(
                sum(value.get("status") == "APPROVED" for value in applicable) / max(1, len(applicable)),
                4,
            )
            if key.endswith("_answer")
            else None,
        }
        if key.endswith("retrieval"):
            latencies = sorted(
                float(value.get("latency_ms") or 0.0)
                for value in applicable
                if value.get("latency_ms") is not None
            )
            summary[key]["latency_ms"] = {
                "mean": round(sum(latencies) / len(latencies), 2) if latencies else None,
                "p95": (
                    round(latencies[max(0, math.ceil(len(latencies) * 0.95) - 1)], 2)
                    if latencies
                    else None
                ),
            }
            summary[key]["retrieval_coverage"] = _retrieval_coverage_summary(applicable)
            summary[key]["reviewed_relevance"] = _reviewed_relevance_summary(rows, key)
            summary[key]["reviewed_document_relevance"] = (
                _reviewed_relevance_summary(rows, key, match_scope="document")
            )
            summary[key]["reviewed_section_relevance"] = (
                _reviewed_relevance_summary(rows, key, match_scope="section")
            )
    for pipeline in ("current", "vnext"):
        retrieved_answers = [
            row[f"{pipeline}_answer"]
            for row in rows
            if (row.get(f"{pipeline}_retrieval") or {}).get("status") == "RESULT"
            and isinstance(row.get(f"{pipeline}_answer"), dict)
        ]
        if retrieved_answers:
            summary[f"{pipeline}_grounded_answer_coverage"] = (
                _grounded_answer_coverage(retrieved_answers)
            )
    return summary


def _grounded_answer_coverage(answers: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "retrieved_cases": len(answers),
        "approved": sum(answer.get("status") == "APPROVED" for answer in answers),
        "safe_abstentions": sum(
            answer.get("status") == "SAFE_ABSTENTION" for answer in answers
        ),
        "review_required": sum(
            answer.get("status") == "NUMERIC_REVIEW_REQUIRED" for answer in answers
        ),
        "contract_failures": sum(
            answer.get("status") in {"ERROR", "EVIDENCE_CONTRACT_REJECTED"}
            for answer in answers
        ),
        "approved_rate": round(
            sum(answer.get("status") == "APPROVED" for answer in answers)
            / len(answers),
            4,
        ),
    }


def _retrieval_coverage_summary(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    """Separate intentional routing from retrieval-required evidence coverage."""
    routed_by_intent: dict[str, int] = {}
    retrieval_required: list[dict[str, Any]] = []
    routed: list[dict[str, Any]] = []
    for snapshot in snapshots:
        intent = str(snapshot.get("conversation_intent") or "knowledge").strip().lower()
        if intent and intent != "knowledge":
            routed.append(snapshot)
            routed_by_intent[intent] = routed_by_intent.get(intent, 0) + 1
        else:
            retrieval_required.append(snapshot)

    returned_evidence = sum(
        snapshot.get("status") == "RESULT" for snapshot in retrieval_required
    )
    no_evidence = sum(
        snapshot.get("status") == "NO_RESULT" for snapshot in retrieval_required
    )
    errors = sum(snapshot.get("status") == "ERROR" for snapshot in retrieval_required)
    return {
        "retrieval_required_cases": len(retrieval_required),
        "returned_evidence": returned_evidence,
        "knowledge_no_evidence": no_evidence,
        "retrieval_errors": errors,
        "retrieval_required_coverage_rate": round(
            returned_evidence / max(1, len(retrieval_required)),
            4,
        ),
        "intentionally_routed_cases": len(routed),
        "routed_by_intent": dict(sorted(routed_by_intent.items())),
    }


def _normalized_section_id(value: str) -> str:
    normalized = re.sub(
        r"[\s_]+",
        "-",
        str(value or "").strip().casefold(),
    ).strip("-.")
    normalized = re.sub(
        r"-(?:part|fact|definition|occurrence)-?\d+.*$",
        "",
        normalized,
    )
    normalized = re.sub(r"^(\d+(?:\.\d+)*?)-[a-z]$", r"\1", normalized)
    return normalized


def _best_expected_rank(
    snapshot: dict[str, Any],
    label: dict[str, Any],
    *,
    match_scope: str = "any",
) -> int | None:
    expected_sources = {
        str(value).strip().casefold()
        for value in label.get("expected_source_uris", [])
        if str(value).strip()
    }
    expected_names = {
        str(value).strip().casefold()
        for value in label.get("expected_document_names", [])
        if str(value).strip()
    }
    expected_documents = {
        str(value).strip().casefold()
        for value in label.get("expected_document_ids", [])
        if str(value).strip()
    }
    expected_sections = {
        _normalized_section_id(str(value))
        for value in label.get("expected_section_ids", [])
        if str(value).strip()
    }
    for fallback_rank, document in enumerate(snapshot.get("documents") or [], start=1):
        source = str(document.get("source") or "").strip().casefold()
        source_name = source.rsplit("/", 1)[-1]
        document_id = str(document.get("id") or "").strip().casefold()
        section_id = _normalized_section_id(str(document.get("section") or ""))
        document_match = (
            source in expected_sources
            or source_name in expected_names
            or document_id in expected_documents
        )
        section_match = section_id in expected_sections
        if (
            (match_scope == "document" and document_match)
            or (match_scope == "section" and section_match)
            or (match_scope == "any" and (document_match or section_match))
        ):
            return int(document.get("rank") or fallback_rank)
    return None


def _reviewed_relevance_summary(
    rows: list[dict[str, Any]],
    retrieval_key: str,
    *,
    match_scope: str = "any",
) -> dict[str, Any]:
    """Calculate retrieval relevance only from human-approved gold labels."""
    ranks: list[int | None] = []
    for row in rows:
        label = row.get("expected_evidence")
        snapshot = row.get(retrieval_key)
        if not isinstance(label, dict) or not isinstance(snapshot, dict):
            continue
        if match_scope == "document" and not any(
            label.get(field)
            for field in (
                "expected_source_uris",
                "expected_document_names",
                "expected_document_ids",
            )
        ):
            continue
        if match_scope == "section" and not label.get("expected_section_ids"):
            continue
        ranks.append(_best_expected_rank(snapshot, label, match_scope=match_scope))
    labeled = len(ranks)
    return {
        "approved_labeled_cases": labeled,
        "recall_at_1": round(
            sum(rank is not None and rank <= 1 for rank in ranks) / max(1, labeled),
            4,
        ),
        "recall_at_3": round(
            sum(rank is not None and rank <= 3 for rank in ranks) / max(1, labeled),
            4,
        ),
        "recall_at_5": round(
            sum(rank is not None and rank <= 5 for rank in ranks) / max(1, labeled),
            4,
        ),
        "recall_at_10": round(
            sum(rank is not None and rank <= 10 for rank in ranks) / max(1, labeled),
            4,
        ),
        "mean_reciprocal_rank": round(
            sum(1.0 / rank for rank in ranks if rank is not None) / max(1, labeled),
            4,
        ),
        "expected_evidence_not_found": sum(rank is None for rank in ranks),
    }


def _write_result_reports(
    rows: list[dict[str, Any]],
    output_dir: Path,
    run_name: str,
) -> tuple[Path, Path, Path]:
    summary_path = output_dir / f"{run_name}-summary.json"
    review_path = output_dir / f"{run_name}-review.csv"
    summary_path.write_text(
        json.dumps(_result_summary(rows), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    fields = [
        "case_index",
        "case_id",
        "country",
        "language",
        "question",
        "rating",
        "reviewer_comment",
        "current_status",
        "current_confidence",
        "current_top_source",
        "current_answer_status",
        "current_answer",
        "vnext_status",
        "vnext_confidence",
        "vnext_top_source",
        "vnext_answer_status",
        "vnext_answer",
        "human_verdict",
        "human_notes",
    ]
    with review_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            current = row.get("current_retrieval", {})
            current_answer = row.get("current_answer", {})
            vnext = row.get("vnext_retrieval", {})
            answer = row.get("vnext_answer", {})
            writer.writerow(
                {
                    "case_index": row["case_index"],
                    "case_id": row["case_id"],
                    "country": row["country"],
                    "language": row["language"],
                    "question": row["question"],
                    "rating": row.get("rating"),
                    "reviewer_comment": row.get("reviewer_comment", ""),
                    "current_status": current.get("status", ""),
                    "current_confidence": current.get("confidence", ""),
                    "current_top_source": json.dumps((current.get("documents") or [{}])[0], ensure_ascii=False),
                    "current_answer_status": current_answer.get("status", ""),
                    "current_answer": current_answer.get("answer", ""),
                    "vnext_status": vnext.get("status", ""),
                    "vnext_confidence": vnext.get("confidence", ""),
                    "vnext_top_source": json.dumps((vnext.get("documents") or [{}])[0], ensure_ascii=False),
                    "vnext_answer_status": answer.get("status", ""),
                    "vnext_answer": answer.get("answer", ""),
                    "human_verdict": "",
                    "human_notes": "",
                }
            )
    outcome_path = _write_answer_outcome_diagnostics(rows, output_dir, run_name)
    return summary_path, review_path, outcome_path


def _answer_outcome_reason(status: str) -> str:
    return {
        "SAFE_ABSTENTION": "model_declared_insufficient_evidence",
        "NUMERIC_REVIEW_REQUIRED": "numeric_claim_not_supported_by_selected_evidence",
        "EVIDENCE_CONTRACT_REJECTED": "invalid_evidence_contract_after_retry",
        "ERROR": "answer_generation_error",
        "NO_EVIDENCE": "retrieval_returned_no_evidence",
    }.get(status, "")


def _write_answer_outcome_diagnostics(
    rows: list[dict[str, Any]],
    output_dir: Path,
    run_name: str,
) -> Path:
    """Write exceptional answer outcomes without deciding human correctness."""
    path = output_dir / f"{run_name}-answer-outcomes.csv"
    fields = [
        "case_index",
        "case_id",
        "country",
        "language",
        "question",
        "pipeline",
        "answer_status",
        "diagnostic_reason",
        "retrieval_status",
        "retrieval_confidence",
        "retrieved_source_ids",
        "retrieved_excerpts",
        "unsupported_numeric_claims",
        "contract_error",
        "raw_response",
        "human_outcome_verdict",
        "human_notes",
    ]
    exceptional_statuses = {
        "SAFE_ABSTENTION",
        "NUMERIC_REVIEW_REQUIRED",
        "EVIDENCE_CONTRACT_REJECTED",
        "ERROR",
        "NO_EVIDENCE",
    }
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            for pipeline in ("current", "vnext"):
                answer = row.get(f"{pipeline}_answer") or {}
                status = str(answer.get("status") or "")
                if status not in exceptional_statuses:
                    continue
                retrieval = row.get(f"{pipeline}_retrieval") or {}
                documents = list(retrieval.get("documents") or [])
                writer.writerow(
                    {
                        "case_index": row.get("case_index", ""),
                        "case_id": row.get("case_id", ""),
                        "country": row.get("country", ""),
                        "language": row.get("language", ""),
                        "question": row.get("question", ""),
                        "pipeline": pipeline,
                        "answer_status": status,
                        "diagnostic_reason": _answer_outcome_reason(status),
                        "retrieval_status": retrieval.get("status", ""),
                        "retrieval_confidence": retrieval.get("confidence", ""),
                        "retrieved_source_ids": " | ".join(
                            str(document.get("id") or "") for document in documents
                        ),
                        "retrieved_excerpts": "\n\n".join(
                            str(document.get("excerpt") or "")
                            for document in documents[:3]
                        ),
                        "unsupported_numeric_claims": " | ".join(
                            str(claim)
                            for claim in answer.get("unsupported_numeric_claims") or []
                        ),
                        "contract_error": answer.get("error", ""),
                        "raw_response": answer.get("raw_response", ""),
                        "human_outcome_verdict": "",
                        "human_notes": "",
                    }
                )
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Markdown interaction-history table.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "interaction_quality",
    )
    parser.add_argument(
        "--pipeline",
        choices=["inventory", "current", "vnext", "both"],
        default="inventory",
    )
    parser.add_argument(
        "--vnext-profile",
        choices=sorted(VNEXT_PROFILE_FEATURES),
        default="full",
        help="Run one isolated retrieval feature or the complete vNext profile.",
    )
    parser.add_argument(
        "--vnext-index",
        default=None,
        help="Explicit isolated vNext index. This overrides loaded configuration for this run.",
    )
    parser.add_argument(
        "--allow-same-index-rank-ablation",
        action="store_true",
        help=(
            "Allow a paired rank-* profile to read the production index for both pipelines. "
            "This evaluator is read-only and still shares one immutable query plan."
        ),
    )
    parser.add_argument(
        "--rank-ablation-current-selector",
        action="store_true",
        help=(
            "Keep the current pipeline's evidence selector enabled during a same-index "
            "rank ablation. Use this to measure selector-only impact against production behavior."
        ),
    )
    parser.add_argument(
        "--rank-ablation-disable-current-glossary",
        action="store_true",
        help=(
            "Disable the current pipeline glossary during a same-index rank ablation. "
            "Use with a glossary-enabled profile to isolate glossary expansion."
        ),
    )
    parser.add_argument("--generate-answers", action="store_true")
    parser.add_argument("--rated-only", action="store_true")
    parser.add_argument("--start-at", type=int, default=1)
    parser.add_argument("--max-cases", type=int, default=0, help="Zero evaluates every selected row.")
    parser.add_argument("--sleep-ms", type=int, default=0)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=1)
    parser.add_argument("--run-name", default="interaction-vnext-evaluation")
    parser.add_argument(
        "--expected-evidence-labels",
        type=Path,
        default=None,
        help="Reviewed CSV with expected document/section IDs. A template is created when absent.",
    )
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--retry-errors", action="store_true")
    parser.add_argument(
        "--retry-answer-status",
        action="append",
        default=[],
        choices=["EVIDENCE_CONTRACT_REJECTED", "NUMERIC_REVIEW_REQUIRED"],
        help="Re-run checkpoint rows with this vNext answer status.",
    )
    parser.add_argument("--allow-parse-issues", action="store_true")
    parser.add_argument("--load-ssm", action="store_true")
    parser.add_argument("--quiet", action="store_true", help="Hide routine provider logs.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.expected_evidence_labels is None:
        args.expected_evidence_labels = args.output_dir / "expected_evidence_labels.csv"
    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)
    if not args.input.exists():
        print(f"Input not found: {args.input}", file=sys.stderr)
        return 2
    if args.load_ssm:
        settings.load_ssm_config()
    if args.allow_same_index_rank_ablation:
        if args.pipeline != "both" or not args.vnext_profile.startswith("rank-"):
            print(
                "--allow-same-index-rank-ablation requires --pipeline both and a rank-* profile.",
                file=sys.stderr,
            )
            return 2
        selected_index = str(args.vnext_index or settings.OPENSEARCH_VNEXT_INDEX).strip()
        if selected_index != settings.OPENSEARCH_INDEX:
            print(
                "--allow-same-index-rank-ablation requires --vnext-index to equal OPENSEARCH_INDEX.",
                file=sys.stderr,
            )
            return 2

    cases, issues = parse_interaction_history(args.input)
    outputs = _write_inventory(cases, issues, args.output_dir)
    outputs["expected_evidence_labels"] = _write_expected_evidence_template(
        cases,
        args.expected_evidence_labels,
    )
    summary = dataset_summary(cases, issues)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    for name, path in outputs.items():
        print(f"{name}: {path}")
    if issues and not args.allow_parse_issues:
        print("Parse issues found; retrieval evaluation was not started.", file=sys.stderr)
        return 1
    if args.pipeline == "inventory":
        return 0

    checkpoint, rows = _evaluate_cases(args, cases)
    summary_path, review_path, outcome_path = _write_result_reports(
        rows,
        args.output_dir,
        args.run_name,
    )
    print(json.dumps(_result_summary(rows), indent=2, ensure_ascii=False))
    print(f"checkpoint: {checkpoint}")
    print(f"summary: {summary_path}")
    print(f"review: {review_path}")
    print(f"answer_outcomes: {outcome_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
