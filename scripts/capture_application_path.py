"""Capture the real application path for a manifest of multi-turn cases.

The old retrieval-only capture (``scripts/evidence_first_v2/
capture_read_only_retrieval.py``) loops over a bare question string and never
reads stored conversation turns, so a multi-turn case (Tanzania's "And what
about FBOs who live there?", Finland's "Entä jos hän...") was captured as if
it were a brand-new first turn. R03 made that runner fail closed on any case
with stored turns (see docs/evidence_first_v2/TERRA-R03-CONTEXT-TO-CAPTURE-
20260918-1400.md); this file is the replacement for cases that actually need
history. It drives the real ``AIOrchestrator.handle_chat`` with the manifest's
stored turns seeded into the session's memory backend, exactly the way the
offline tests seed it (``services.session`` with
``settings.CHAT_MEMORY_BACKEND == "memory"``), so the orchestrator resolves
its own follow-up continuity instead of the tool guessing at it.

This module must never be imported or run against real AWS, OpenSearch,
Bedrock or any network service by anyone preparing or testing it. ``
--preflight`` is the only mode meant to run outside of an approved, live
capture, and it is deliberately built to import nothing that could construct
a real client. A live (non-preflight) run additionally refuses to start
without an explicit ``--i-have-approval <approval-id>`` argument.

See docs/conversation-quality/phase2/R09_CAPTURE_PLAN.md for the manifest
schema, the first proposed manifest outline, the preflight command, the call/
cost envelope formula, and the exact approval text a run needs.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

CAPTURE_SCHEMA_VERSION = 1
MANIFEST_VERSION = 1

REQUIRED_TOP_LEVEL_KEYS = {"manifest_version", "cases"}
REQUIRED_CASE_KEYS = {
    "id", "split", "exposure", "turns", "message", "country", "language", "role", "expectations",
}
REQUIRED_TURN_KEYS = {"user", "assistant"}
ALLOWED_SPLITS = {"development", "evaluation"}

# Per-case upper bound on external calls, used only by --preflight's estimate.
# One question can, in the worst case (query planner enabled, several planned
# queries, each searching a text/vector/global-text/global-vector channel,
# plus one evidence-selector call and one generation call), reach roughly this
# many calls. It is a documented ceiling, not a measurement: --preflight makes
# no calls at all, so it cannot count anything real.
MAX_PLANNED_QUERIES_PER_CASE = 4
CHANNELS_PER_QUERY = 4  # text, vector, global_text, global_vector
MAX_RETRIEVAL_CALLS_PER_CASE = MAX_PLANNED_QUERIES_PER_CASE * CHANNELS_PER_QUERY
MAX_EMBEDDING_CALLS_PER_CASE = MAX_PLANNED_QUERIES_PER_CASE  # one embedding per vector channel query
MAX_PLANNER_CALLS_PER_CASE = 2  # the query planner call plus one global-document translation call
MAX_SELECTOR_CALLS_PER_CASE = 1
MAX_RERANKER_CALLS_PER_CASE = 1
MAX_GENERATION_CALLS_PER_CASE = 1
CALL_CATEGORIES = ("retrieval", "embedding", "planner_or_translation", "selector", "reranker", "generation")
MAX_CALLS_PER_CASE = {
    "retrieval": MAX_RETRIEVAL_CALLS_PER_CASE,
    "embedding": MAX_EMBEDDING_CALLS_PER_CASE,
    "planner_or_translation": MAX_PLANNER_CALLS_PER_CASE,
    "selector": MAX_SELECTOR_CALLS_PER_CASE,
    "reranker": MAX_RERANKER_CALLS_PER_CASE,
    "generation": MAX_GENERATION_CALLS_PER_CASE,
}

# Settings recorded per case. This is an explicit whitelist, not a denylist:
# only names on this list are ever read from config.settings, and every name
# is additionally screened by _looks_credential_like before being written.
# Nothing outside this list -- including RDS/Cognito/widget/admin secrets --
# is ever touched.
SETTINGS_WHITELIST = (
    "APP_ENV", "APP_VERSION", "PROMPT_VERSION", "KB_VERSION", "RETRIEVAL_PIPELINE_VERSION",
    "RESPONSE_PIPELINE_VERSION", "CONVERSATION_ROUTING_VERSION", "MODEL_ROUTING_VERSION",
    "DEFAULT_MODEL_PROVIDER", "MODEL_ROUTING_MODE", "BEDROCK_FAST_MODEL_ID", "BEDROCK_COMPLEX_MODEL_ID",
    "BEDROCK_EMBED_MODEL_ID", "BEDROCK_MAX_OUTPUT_TOKENS", "BEDROCK_CLASSIFIER_TEMPERATURE",
    "BEDROCK_MIN_CONFIDENCE", "BEDROCK_RETRIEVAL_RESULT_COUNT", "BEDROCK_RETRIEVAL_CANDIDATE_COUNT",
    "BEDROCK_RETRIEVAL_CONFIGURATION", "BEDROCK_STRONG_LOCAL_MATCH_THRESHOLD",
    "BEDROCK_QUERY_PLANNER_ENABLED", "BEDROCK_QUERY_PLANNER_QUERY_COUNT",
    "BEDROCK_EVIDENCE_SELECTOR_ENABLED", "BEDROCK_EVIDENCE_SELECTOR_CANDIDATE_COUNT",
    "RETRIEVAL_PROVIDER", "OPENSEARCH_RESULT_COUNT", "OPENSEARCH_CANDIDATE_COUNT",
    "OPENSEARCH_GLOSSARY_ENABLED", "OPENSEARCH_LIVE_RERANK_ENABLED",
    "OPENSEARCH_EVIDENCE_SELECTOR_ENABLED", "OPENSEARCH_EVIDENCE_SELECTOR_CANDIDATE_COUNT",
    "OPENSEARCH_RETRIEVAL_HARDENING_ENABLED", "OPENSEARCH_GLOBAL_DOCUMENT_TRANSLATION_ENABLED",
    "RETRIEVAL_PARENT_DIVERSITY_ENABLED", "RETRIEVAL_MAX_RESULTS_PER_PARENT",
    "EMBEDDING_SHARED_CACHE_ENABLED", "FALLBACK_OFFICE_CONTACT_ENABLED", "EVIDENCE_GATED_OUTPUT_ENABLED",
    "CHAT_MEMORY_BACKEND", "CHAT_HISTORY_MAX_MESSAGES", "SEMANTIC_CACHE_ENABLED",
    "SEMANTIC_CACHE_SHADOW_ENABLED", "CANDIDATE_MODE_LOOKUP_ENABLED", "LEGAL_VERSION",
)
_CREDENTIAL_LIKE_MARKERS = ("SECRET", "PASSWORD", "TOKEN", "CREDENTIAL", "_ARN", "CLIENT_ID", "API_KEY")


class ManifestError(ValueError):
    """Raised when a manifest fails strict validation."""


class ResumeMismatchError(ValueError):
    """Raised when --resume's checkpoint does not match the current run."""


class ApprovalRequiredError(ValueError):
    """Raised when a live capture is attempted without --i-have-approval."""


class CallBudgetExceeded(RuntimeError):
    """Raised internally to abort a run cleanly once a cap is exceeded."""


# --------------------------------------------------------------------------
# Manifest loading and strict validation. Pure, offline, no imports of app/.
# --------------------------------------------------------------------------


def canonical_manifest_bytes(manifest: dict[str, Any]) -> bytes:
    """A stable byte encoding used for the manifest's SHA-256 identity."""
    return json.dumps(manifest, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")


def manifest_sha256(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_manifest_bytes(manifest)).hexdigest()


def _fail(path: str, message: str) -> None:
    raise ManifestError(f"{path}: {message}")


def _validate_turn(turn: Any, path: str) -> None:
    if not isinstance(turn, dict):
        _fail(path, "a turn must be an object")
    if set(turn.keys()) != REQUIRED_TURN_KEYS:
        _fail(path, f"a turn must have exactly {sorted(REQUIRED_TURN_KEYS)}, got {sorted(turn.keys())}")
    for key in REQUIRED_TURN_KEYS:
        if not isinstance(turn[key], str):
            _fail(f"{path}.{key}", "must be a string")


def _validate_case(case: Any, index: int, seen_ids: set[str]) -> None:
    path = f"cases[{index}]"
    if not isinstance(case, dict):
        _fail(path, "a case must be an object")
    keys = set(case.keys())
    if keys != REQUIRED_CASE_KEYS:
        missing = REQUIRED_CASE_KEYS - keys
        extra = keys - REQUIRED_CASE_KEYS
        _fail(path, f"missing keys {sorted(missing)}, unexpected keys {sorted(extra)}")

    case_id = case["id"]
    if not isinstance(case_id, str) or not case_id.strip():
        _fail(f"{path}.id", "must be a nonblank string")
    if case_id in seen_ids:
        _fail(f"{path}.id", f"duplicate case id {case_id!r}")
    seen_ids.add(case_id)

    if case["split"] not in ALLOWED_SPLITS:
        _fail(f"{path}.split", f"must be one of {sorted(ALLOWED_SPLITS)}")

    if not isinstance(case["exposure"], str) or not case["exposure"].strip():
        _fail(f"{path}.exposure", "must be a nonblank string honestly describing exposure")

    turns = case["turns"]
    if not isinstance(turns, list):
        _fail(f"{path}.turns", "must be a list")
    for turn_index, turn in enumerate(turns):
        _validate_turn(turn, f"{path}.turns[{turn_index}]")

    if not isinstance(case["message"], str) or not case["message"].strip():
        _fail(f"{path}.message", "must be a nonblank string")

    country = case["country"]
    if not isinstance(country, str) or not country.strip():
        _fail(f"{path}.country", "must be a nonblank string")

    language = case["language"]
    if not isinstance(language, str) or not language.strip():
        _fail(f"{path}.language", "must be a nonblank string")

    role = case["role"]
    if not isinstance(role, str) or not role.strip():
        _fail(f"{path}.role", "must be a nonblank string")

    # expectations is intentionally opaque: any JSON value is accepted here,
    # because this tool must never interpret it. It is data for a human or a
    # later, separate grading step -- never read by the runtime path below.
    if "expectations" not in case:
        _fail(f"{path}.expectations", "must be present, even if empty")


def load_manifest(path: Path) -> tuple[dict[str, Any], str]:
    """Parse and strictly validate a manifest; return it with its SHA-256."""
    raw = path.read_text(encoding="utf-8")
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"invalid JSON: {exc}") from exc

    if not isinstance(manifest, dict):
        _fail("<root>", "manifest must be a JSON object")
    if set(manifest.keys()) != REQUIRED_TOP_LEVEL_KEYS:
        _fail("<root>", f"must have exactly {sorted(REQUIRED_TOP_LEVEL_KEYS)}, got {sorted(manifest.keys())}")
    if manifest["manifest_version"] != MANIFEST_VERSION:
        _fail("manifest_version", f"expected {MANIFEST_VERSION}")

    cases = manifest["cases"]
    if not isinstance(cases, list) or not cases:
        _fail("cases", "must be a nonempty list")

    seen_ids: set[str] = set()
    for index, case in enumerate(cases):
        _validate_case(case, index, seen_ids)

    return manifest, manifest_sha256(manifest)


def _runtime_fields(case: dict[str, Any]) -> dict[str, Any]:
    """The only fields the runtime path is ever handed. Drops `expectations`.

    `exposure` is also dropped here: it describes the manifest, not something
    the orchestrator should see. Only id/split/turns/message/country/language/
    role cross into anything that touches AIOrchestrator.
    """
    return {
        "id": case["id"],
        "split": case["split"],
        "turns": copy.deepcopy(case["turns"]),
        "message": case["message"],
        "country": case["country"],
        "language": case["language"],
        "role": case["role"],
    }


# --------------------------------------------------------------------------
# Code identity, settings snapshot. Both are read-only and offline.
# --------------------------------------------------------------------------


def git_code_identity(repo_root: Path = ROOT) -> dict[str, Any]:
    """Return {"head": <sha>, "dirty": bool} for the working tree, via git."""
    head = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain"],
        capture_output=True, text=True, check=True,
    ).stdout
    return {"head": head, "dirty": bool(status.strip())}


def _looks_credential_like(name: str) -> bool:
    upper = name.upper()
    return any(marker in upper for marker in _CREDENTIAL_LIKE_MARKERS)


def safe_settings_snapshot() -> dict[str, Any]:
    """A whitelisted, credential-screened snapshot of config.settings."""
    from config import settings

    snapshot: dict[str, Any] = {}
    for name in SETTINGS_WHITELIST:
        if _looks_credential_like(name):
            continue  # belt-and-suspenders; none of the whitelist should match
        if not hasattr(settings, name):
            continue
        value = getattr(settings, name)
        if isinstance(value, str) and _looks_credential_like(value):
            continue
        snapshot[name] = value
    return snapshot


# --------------------------------------------------------------------------
# Call accounting: wraps the real boundary callables so every count is an
# actual observed call, never an after-the-fact estimate. Only used by a
# live (non-preflight) run; preflight never imports this section.
# --------------------------------------------------------------------------


def install_call_counters(orchestrator: "Any") -> tuple[dict[str, int], "list[tuple[object, str, object]]"]:
    """Patch the real retrieval/generation boundary; return (counters, patches).

    Restore with `restore_call_counters(patches)`. Counters accumulate across
    every case until reset; callers diff before/after each case.

    `orchestrator.model_router.generate` is wrapped at the *instance* level so
    that a fake router (as every offline test uses) is counted exactly like a
    real `ModelRouter`, instead of silently reading zero because a fake isn't
    the patched class. Retrieval internals are only reachable through the
    real `OpenSearchSectionProvider`, so with a fake retriever those counts
    are honestly zero -- the fake never touches them.
    """
    import app.retrieval.opensearch_sections as opensearch_sections
    from app.retrieval.opensearch_sections import OpenSearchSectionProvider

    counters = {key: 0 for key in CALL_CATEGORIES}
    patches: list[tuple[object, str, object]] = []

    def _wrap(target: object, attr: str, key: str) -> None:
        if not hasattr(target, attr):
            return
        original = getattr(target, attr)

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            counters[key] += 1
            return original(*args, **kwargs)

        patches.append((target, attr, original))
        setattr(target, attr, wrapper)

    # Generation: the final model call that produces the answer. Wrapped on
    # the actual router instance handed to this orchestrator, real or fake.
    _wrap(orchestrator.model_router, "generate", "generation")

    # Retrieval: one call per OpenSearch channel search actually issued.
    _wrap(OpenSearchSectionProvider, "_search_channel", "retrieval")
    # Embedding: one call per vector query actually embedded.
    _wrap(opensearch_sections, "embed_text", "embedding")
    # Planner and the global-document translation call share a bucket: both
    # are pre-retrieval Bedrock Converse calls that shape the query, and
    # today neither exposes a distinguishing structural label at this
    # boundary (see R09_CAPTURE_PLAN.md's interface-request list).
    _wrap(opensearch_sections, "_planned_retrieval_plan", "planner_or_translation")
    _wrap(OpenSearchSectionProvider, "_global_search_query", "planner_or_translation")
    # Evidence selector.
    _wrap(OpenSearchSectionProvider, "_select_evidence_rows", "selector")
    # Reranker: today this is the lexical `_rerank_documents` helper inside
    # app/retrieval/providers.py, not a model call; counted anyway so a
    # future model-backed reranker is covered without changing this script.
    try:
        import app.retrieval.providers as providers

        _wrap(providers, "_rerank_documents", "reranker")
    except Exception:  # noqa: BLE001 - reranker accounting must never block a run
        pass

    return counters, patches


def restore_call_counters(patches: "list[tuple[object, str, object]]") -> None:
    for target, attr, original in patches:
        setattr(target, attr, original)


# --------------------------------------------------------------------------
# Preflight: manifest stats and a call/cost estimate. Zero external calls.
# Deliberately does not import anything under app/ or services/.
# --------------------------------------------------------------------------


def preflight_report(manifest: dict[str, Any], sha: str, unit_prices: dict[str, float]) -> dict[str, Any]:
    cases = manifest["cases"]
    per_split: dict[str, int] = {}
    for case in cases:
        per_split[case["split"]] = per_split.get(case["split"], 0) + 1

    case_count = len(cases)
    max_calls = {key: MAX_CALLS_PER_CASE[key] * case_count for key in CALL_CATEGORIES}
    max_calls["total"] = sum(max_calls[key] for key in CALL_CATEGORIES)

    cost_envelope = None
    if unit_prices:
        cost_envelope = {
            key: round(max_calls[key] * unit_prices.get(key, 0.0), 6)
            for key in CALL_CATEGORIES
            if key in unit_prices
        }
        cost_envelope["total"] = round(sum(cost_envelope.values()), 6)

    return {
        "manifest_sha256": sha,
        "case_count": case_count,
        "cases_per_split": per_split,
        "max_calls_per_case_by_category": dict(MAX_CALLS_PER_CASE),
        "max_calls_formula": (
            "max_calls[category] = MAX_CALLS_PER_CASE[category] * case_count; "
            "MAX_CALLS_PER_CASE derives from "
            f"MAX_PLANNED_QUERIES_PER_CASE={MAX_PLANNED_QUERIES_PER_CASE} "
            f"* CHANNELS_PER_QUERY={CHANNELS_PER_QUERY} for retrieval, "
            f"MAX_PLANNED_QUERIES_PER_CASE for embedding, and small fixed "
            "per-case ceilings for planner_or_translation/selector/reranker/generation "
            "(see the MAX_*_CALLS_PER_CASE constants in this file)."
        ),
        "max_calls_total": max_calls,
        "cost_envelope": cost_envelope,
        "cost_envelope_note": (
            "None of these unit prices are hard-coded; pass --unit-price NAME=PRICE "
            "(NAME one of retrieval/embedding/planner_or_translation/selector/reranker/"
            "generation) to compute an envelope. Omitted categories are left out of "
            "the total rather than assumed free."
        ),
    }


# --------------------------------------------------------------------------
# Live capture: drives the real AIOrchestrator.handle_chat with seeded
# session history. Only reachable from a non-preflight run that has passed
# --i-have-approval.
# --------------------------------------------------------------------------


def _seed_session_history(session_id: str, turns: list[dict[str, str]], correlation_id: str) -> None:
    """Write stored prior turns into the memory session backend.

    Mirrors `tests/unit/test_chat_orchestrator.py`'s own fixture: the memory
    backend is process-local and never touches Postgres. The caller is
    responsible for setting `settings.CHAT_MEMORY_BACKEND = "memory"` and for
    giving each case its own `session_id` so no case's history can bleed into
    another's.
    """
    from services.session import append_session_turn

    for turn in turns:
        append_session_turn(session_id, turn["user"], turn["assistant"], correlation_id)


def _extract_retrieval_rank_lists(diagnostic_capture: dict[str, Any] | None) -> dict[str, Any] | None:
    if not diagnostic_capture:
        return None
    for retrieval in reversed(diagnostic_capture.get("retrievals", [])):
        rank_lists = (retrieval.get("metadata") or {}).get("retrieval_rank_lists")
        if rank_lists is not None:
            return rank_lists
    return None


def _question_retrieval_field(diagnostic_capture: dict[str, Any] | None, key: str) -> Any:
    """Return `key` from the question-stage retrieval record, or "unavailable" if none was recorded."""
    if not diagnostic_capture:
        return "unavailable"
    for retrieval in diagnostic_capture.get("retrievals", []):
        if retrieval.get("stage") == "question" and key in retrieval:
            return retrieval[key]
    return "unavailable"


def _extract_ingestion_ids(diagnostic_capture: dict[str, Any] | None) -> list[str]:
    if not diagnostic_capture:
        return []
    ids: set[str] = set()
    for retrieval in diagnostic_capture.get("retrievals", []):
        for document in retrieval.get("documents", []):
            ingestion_id = document.get("ingestion_id")
            if ingestion_id:
                ids.add(str(ingestion_id))
    return sorted(ids)


def run_one_case(
    orchestrator: "Any",
    case: dict[str, Any],
    *,
    correlation_id: str,
    capture_final_answer: bool,
) -> dict[str, Any]:
    """Drive one manifest case through the real application path.

    `case` must already be the stripped runtime view from `_runtime_fields` --
    this function never receives or reads `expectations`.
    """
    from app.orchestrator import chat_orchestrator
    from utils.validators import ChatRequest

    session_id = f"capture-{case['id']}"
    _seed_session_history(session_id, case["turns"], correlation_id)

    resolved_query = "unavailable"
    context_resolution_precall = "unavailable"
    try:
        from services.session import get_session_history

        history = get_session_history(session_id, correlation_id)
        resolved_query, context_resolution_precall = orchestrator._build_retrieval_query_with_provenance(
            case["message"], history, correlation_id, session_id=session_id,
        )
    except Exception as exc:  # noqa: BLE001 - recording must never block the real call below
        context_resolution_precall = {"error": str(exc)}

    counters, patches = install_call_counters(orchestrator)
    # Diagnostic capture (retrieval_rank_lists, per-turn context provenance)
    # is off by default and shared module state; scope it to this one case's
    # call so a capture run never leaves it enabled for anything else in the
    # same process.
    previous_capture_flag = chat_orchestrator.DIAGNOSTIC_CAPTURE_ENABLED
    chat_orchestrator.DIAGNOSTIC_CAPTURE_ENABLED = True
    started = perf_counter()
    case_error = None
    response = None
    try:
        response = orchestrator.handle_chat(
            ChatRequest(
                message=case["message"], sessionId=session_id,
                country=case["country"], language=case["language"], role=case["role"],
            ),
            correlation_id,
        )
    except Exception as exc:  # noqa: BLE001 - one case's failure must not stop the run
        case_error = f"{type(exc).__name__}: {exc}"
    finally:
        latency_seconds = perf_counter() - started
        call_counts = dict(counters)
        restore_call_counters(patches)
        chat_orchestrator.DIAGNOSTIC_CAPTURE_ENABLED = previous_capture_flag

    diagnostic_capture = None
    if response is not None:
        diagnostic_capture = response.metadata.get("diagnostic_capture") if response.metadata else None
    rank_lists = _extract_retrieval_rank_lists(diagnostic_capture)

    record: dict[str, Any] = {
        "capture_schema_version": CAPTURE_SCHEMA_VERSION,
        "case_id": case["id"],
        "split": case["split"],
        "country": case["country"],
        "language": case["language"],
        "role": case["role"],
        "original_message": case["message"],
        "resolved_query": resolved_query,
        "context_resolution": context_resolution_precall,
        "context_resolution_at_retrieval": (rank_lists or {}).get("context_resolution", "unavailable")
        if rank_lists is not None else "unavailable",
        "runtime_scope_intent": (rank_lists or {}).get("runtime_scope_intent", "unavailable")
        if rank_lists is not None else "unavailable",
        "authorized_policy_market": (rank_lists or {}).get("authorized_policy_market", "unavailable")
        if rank_lists is not None else "unavailable",
        # No field distinct from runtime_scope_intent currently exposes a
        # separate "directory target"; see R09_CAPTURE_PLAN.md's interface
        # requests.
        "directory_target": "unavailable",
        "source_identity": {
            "ingestion_ids": _extract_ingestion_ids(diagnostic_capture) or "unavailable",
            "index_name": getattr(getattr(orchestrator.retriever, "provider", None), "index_name", "unavailable"),
        },
        # R02 provider state from the orchestrator's diagnostic record of the
        # question retrieval: "available", "degraded" or "unavailable", plus the
        # failed channels. "unavailable" here only means no retrieval was
        # recorded (e.g. an early clarification), not a provider outage.
        "retrieval_availability": _question_retrieval_field(diagnostic_capture, "availability"),
        "search_channel_failures": _question_retrieval_field(diagnostic_capture, "failed_search_channels"),
        "candidates_and_ranks": rank_lists if rank_lists is not None else "unavailable",
        "selector": {
            "outcome": (rank_lists or {}).get("selector_outcome"),
            "selected_ranks": (rank_lists or {}).get("selector_selected_ranks"),
            "relevant_evidence": (rank_lists or {}).get("selector_relevant_evidence"),
        } if rank_lists is not None else "unavailable",
        "approved_evidence": response.citations if response is not None else [],
        "call_counts": call_counts,
        "latency_seconds": round(latency_seconds, 6),
        "capture_errors": (diagnostic_capture or {}).get("errors", []) if diagnostic_capture else [],
        "case_error": case_error,
    }
    if capture_final_answer:
        record["final_answer"] = {
            "answer": response.answer if response is not None else None,
            "failure_layer": (response.metadata or {}).get("failure_layer") if response is not None else None,
        }
    return record


# --------------------------------------------------------------------------
# Checkpointing and resume.
# --------------------------------------------------------------------------


def _run_header(manifest_sha: str, approval_id: str) -> dict[str, Any]:
    from config import settings

    return {
        "capture_schema_version": CAPTURE_SCHEMA_VERSION,
        "kind": "run_header",
        "approval_id": approval_id,
        "manifest_sha256": manifest_sha,
        "code_identity": git_code_identity(),
        "prompt_version": settings.PROMPT_VERSION,
        "settings_snapshot": safe_settings_snapshot(),
    }


def read_checkpoint(path: Path) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Return (header, case_rows) from an existing checkpoint, or (None, [])."""
    if not path.exists():
        return None, []
    header = None
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("kind") == "run_header":
                header = record
            else:
                rows.append(record)
    return header, rows


def validate_resume(
    header: dict[str, Any], manifest_sha: str, approval_id: str,
) -> None:
    from config import settings

    current_head = git_code_identity()
    current_prompt_version = settings.PROMPT_VERSION
    mismatches = []
    if header.get("manifest_sha256") != manifest_sha:
        mismatches.append("manifest_sha256")
    if header.get("code_identity") != current_head:
        mismatches.append("code_identity")
    if header.get("prompt_version") != current_prompt_version:
        mismatches.append("prompt_version")
    # One checkpoint is one authorization. Resuming under a different approval
    # would write rows whose approval_id disagrees with the header (Fable
    # re-review, 2026-09-18).
    if header.get("approval_id") != approval_id:
        mismatches.append("approval_id")
    if mismatches:
        raise ResumeMismatchError(
            "refusing to resume: " + ", ".join(mismatches) + " differ from the checkpoint's run header; "
            "a resume must never mix candidate versions or approvals in one output"
        )


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _parse_unit_prices(pairs: list[str]) -> dict[str, float]:
    prices: dict[str, float] = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"--unit-price expects NAME=PRICE, got {pair!r}")
        name, value = pair.split("=", 1)
        name = name.strip()
        if name not in CALL_CATEGORIES:
            raise ValueError(f"--unit-price NAME must be one of {CALL_CATEGORIES}, got {name!r}")
        prices[name] = float(value)
    return prices


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True, help="Path to the case manifest JSON.")
    parser.add_argument("--out", type=Path, help="Checkpoint JSONL path (required unless --preflight).")
    parser.add_argument("--preflight", action="store_true", help="Validate and estimate only; zero external calls.")
    parser.add_argument("--resume", action="store_true", help="Resume an existing checkpoint at --out.")
    parser.add_argument("--i-have-approval", dest="approval_id", default=None, help="Required for a live capture.")
    parser.add_argument("--max-calls", type=int, default=None, help="Abort once total calls exceed this.")
    parser.add_argument("--max-cost", type=float, default=None, help="Abort once estimated cost exceeds this.")
    parser.add_argument(
        "--unit-price", dest="unit_prices", action="append", default=[],
        help="NAME=PRICE, one of retrieval/embedding/planner_or_translation/selector/reranker/generation. "
        "Repeatable. No default prices are built in.",
    )
    parser.add_argument(
        "--capture-final-answer", action="store_true",
        help="Also record the final answer text and failure_layer. Off by default.",
    )
    return parser


def _print_preflight(report: dict[str, Any]) -> None:
    print(json.dumps(report, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:  # noqa: C901
    parser = build_parser()
    args = parser.parse_args(argv)

    manifest, sha = load_manifest(args.manifest)
    unit_prices = _parse_unit_prices(args.unit_prices)

    if args.preflight:
        _print_preflight(preflight_report(manifest, sha, unit_prices))
        return 0

    if not args.out:
        parser.error("--out is required for a live capture")
    if not args.approval_id:
        raise ApprovalRequiredError(
            "a live capture refuses to start without --i-have-approval <approval-id>"
        )

    header, existing_rows = (None, [])
    if args.resume:
        header, existing_rows = read_checkpoint(args.out)
        if header is None:
            raise ResumeMismatchError(f"--resume given but no run header found in {args.out}")
        validate_resume(header, sha, args.approval_id)
    else:
        header = _run_header(sha, args.approval_id)

    done_ids = {row["case_id"] for row in existing_rows if "case_id" in row}

    from app.orchestrator.chat_orchestrator import AIOrchestrator
    from config import settings

    # Seeding stored turns requires the memory session backend (see
    # `_seed_session_history`'s docstring); restore whatever backend was
    # configured before this run touches anything else in the process.
    previous_memory_backend = settings.CHAT_MEMORY_BACKEND
    settings.CHAT_MEMORY_BACKEND = "memory"

    orchestrator = AIOrchestrator()

    mode = "a" if (args.resume and args.out.exists()) else "w"
    running_totals = {key: 0 for key in CALL_CATEGORIES}
    for row in existing_rows:
        for key, value in (row.get("call_counts") or {}).items():
            running_totals[key] = running_totals.get(key, 0) + value

    try:
        with args.out.open(mode, encoding="utf-8") as handle:
            if mode == "w":
                handle.write(json.dumps(header) + "\n")
                handle.flush()

            for index, case in enumerate(manifest["cases"]):
                if case["id"] in done_ids:
                    continue

                record = run_one_case(
                    orchestrator,
                    _runtime_fields(case),
                    correlation_id=f"capture-{case['id']}",
                    capture_final_answer=args.capture_final_answer,
                )
                record["approval_id"] = args.approval_id
                record["exposure"] = case["exposure"]

                for key, value in record["call_counts"].items():
                    running_totals[key] = running_totals.get(key, 0) + value
                total_calls = sum(running_totals.values())

                handle.write(json.dumps(record) + "\n")
                handle.flush()

                if args.max_calls is not None and total_calls > args.max_calls:
                    print(
                        f"max-calls exceeded ({total_calls} > {args.max_calls}); checkpoint written, aborting",
                        file=sys.stderr,
                    )
                    return 2
                if args.max_cost is not None and unit_prices:
                    total_cost = sum(running_totals[key] * unit_prices.get(key, 0.0) for key in CALL_CATEGORIES)
                    if total_cost > args.max_cost:
                        print(
                            f"max-cost exceeded ({total_cost} > {args.max_cost}); checkpoint written, aborting",
                            file=sys.stderr,
                        )
                        return 2

        return 0
    finally:
        settings.CHAT_MEMORY_BACKEND = previous_memory_backend


if __name__ == "__main__":
    sys.exit(main())
