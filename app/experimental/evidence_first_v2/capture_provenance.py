"""Strict, offline-only validation for V2 capture provenance."""

from __future__ import annotations

import re
from typing import Any, Mapping


_SCOPE_PAIRS = frozenset({
    ("policy", "deterministic_policy_route"),
    ("policy", "deterministic_policy_safety_route"),
    ("policy", "local_policy_only"),
    ("directory", "deterministic_directory_route"),
    ("international_sponsoring", "deterministic_sponsoring_route"),
    ("ambiguous", "planner_global_scope_only"),
    ("unknown", "planner_disabled"),
    ("unknown", "planner_unavailable"),
})
_CONTEXT_STATUSES = frozenset({"not_dependent", "resolved_dependent_follow_up", "unresolved", "unknown"})
_PRIOR_TURN_ID = re.compile(r"history-user-[1-9][0-9]*-[0-9a-f]{16}\Z")


def validate_runtime_scope_intent(value: Any) -> dict[str, str] | None:
    """Accept only one exact runtime intent/source pair, or a legacy null."""
    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != {"provenance", "intent", "decision_source"}:
        raise ValueError("runtime_scope_intent must have exactly provenance, intent, and decision_source")
    provenance = value.get("provenance")
    intent = value.get("intent")
    source = value.get("decision_source")
    if provenance != "runtime" or not isinstance(intent, str) or not isinstance(source, str) or (intent, source) not in _SCOPE_PAIRS:
        raise ValueError("runtime_scope_intent is not an allowed runtime intent/source pair")
    return {"provenance": provenance, "intent": intent, "decision_source": source}


def validate_authorized_policy_market(value: Any) -> str | None:
    """Accept an explicit uppercase two-letter market, never a replay substitute."""
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z]{2}", value):
        raise ValueError("authorized_policy_market must be an uppercase two-letter market or null")
    return value


def validate_context_resolution(value: Any) -> dict[str, str] | None:
    """Accept only exact runtime context records and opaque resolved-turn IDs."""
    if value is None:
        return None
    if not isinstance(value, Mapping) or value.get("provenance") != "runtime":
        raise ValueError("context_resolution must be a runtime record")
    status = value.get("status")
    if status not in _CONTEXT_STATUSES:
        raise ValueError("context_resolution has an unsupported status")
    expected = {"provenance", "status", "prior_user_turn_id"} if status == "resolved_dependent_follow_up" else {"provenance", "status"}
    if set(value) != expected:
        raise ValueError("context_resolution has unexpected keys for its status")
    if status == "resolved_dependent_follow_up":
        prior_turn_id = value.get("prior_user_turn_id")
        if not isinstance(prior_turn_id, str) or not _PRIOR_TURN_ID.fullmatch(prior_turn_id):
            raise ValueError("resolved context_resolution requires a valid opaque prior_user_turn_id")
        return {"provenance": "runtime", "status": status, "prior_user_turn_id": prior_turn_id}
    return {"provenance": "runtime", "status": status}


def validate_capture_provenance(
    runtime_scope_intent: Any,
    authorized_policy_market: Any,
    context_resolution: Any,
) -> tuple[dict[str, str] | None, str | None, dict[str, str] | None]:
    """Validate every V2 provenance input at conversion and replay boundaries."""
    return (
        validate_runtime_scope_intent(runtime_scope_intent),
        validate_authorized_policy_market(authorized_policy_market),
        validate_context_resolution(context_resolution),
    )
