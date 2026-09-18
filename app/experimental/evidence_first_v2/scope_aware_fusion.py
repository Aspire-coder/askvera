"""Offline-only, scope-aware fusion for the Evidence-First V2 experiment.

The module consumes captured retrieval lists. It has no route, provider,
network, index, or model dependency and is deliberately not wired into the
application. It never reads expected sections, case identifiers, or judgments.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from .capture_provenance import validate_capture_provenance

_DIRECTORY_INTENTS = frozenset({"directory", "international_sponsoring"})


@dataclass(frozen=True)
class DocumentIdentity:
    """Available fields that make a public document ID trustworthy."""

    public_id: str
    source_file: str
    document_version: str
    content_hash: str
    section_id: str
    country: str
    access_scope: str


@dataclass(frozen=True)
class FusionResult:
    """Deterministic ordering and every scope safeguard that affected it."""

    order: tuple[str, ...]
    scores: tuple[tuple[str, float], ...]
    protected_global_ids: tuple[str, ...]
    rejected_policy_ids: tuple[str, ...]
    used_follow_up_fallback: bool
    context_status: str
    scope_intent_status: str


def _normalized(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).casefold()
    return "".join(char for char in text if char.isalnum())


def _source(hit: Mapping[str, Any]) -> Mapping[str, Any]:
    source = hit.get("_source")
    return source if isinstance(source, Mapping) else {}


def _metadata(hit: Mapping[str, Any]) -> Mapping[str, Any]:
    metadata = _source(hit).get("metadata")
    return metadata if isinstance(metadata, Mapping) else {}


def _identity(hit: Mapping[str, Any]) -> DocumentIdentity:
    source = _source(hit)
    metadata = _metadata(hit)
    public_id = str(source.get("id") or hit.get("_id") or "").strip()
    if not public_id:
        raise ValueError("captured hit lacks a public document id")
    return DocumentIdentity(
        public_id=public_id,
        source_file=str(source.get("source_file") or metadata.get("source_file") or ""),
        document_version=str(source.get("document_version") or metadata.get("document_version") or ""),
        content_hash=str(source.get("content_hash") or metadata.get("content_hash") or ""),
        section_id=str(source.get("section_id") or metadata.get("section_id") or ""),
        country=str(source.get("country") or metadata.get("country") or "").upper(),
        access_scope=str(source.get("access_scope") or metadata.get("access_scope") or "").casefold(),
    )


def _is_global(identity: DocumentIdentity) -> bool:
    return identity.access_scope == "global"


def _eligible(identity: DocumentIdentity, authorized_policy_market: str | None) -> bool:
    if _is_global(identity):
        return True
    return bool(authorized_policy_market and identity.country == authorized_policy_market)


def _scope_intent_status(runtime_scope_intent: Mapping[str, Any] | None) -> str:
    if runtime_scope_intent is None:
        return "missing"
    intent = runtime_scope_intent.get("intent")
    source = runtime_scope_intent.get("decision_source")
    if intent in _DIRECTORY_INTENTS and source in {"deterministic_directory_route", "deterministic_sponsoring_route"}:
        return "directory_compatible"
    if intent in {"ambiguous", "unknown"}:
        return "ambiguous"
    return "policy_or_other"


def _trusted_follow_up(context_resolution: Mapping[str, Any] | None) -> bool:
    return (
        context_resolution is not None
        and context_resolution.get("provenance") == "runtime"
        and context_resolution.get("status") == "resolved_dependent_follow_up"
        and isinstance(context_resolution.get("prior_user_turn_id"), str)
        and bool(context_resolution["prior_user_turn_id"].strip())
    )


def _context_status(context_resolution: Mapping[str, Any] | None) -> str:
    if context_resolution is None:
        return "missing"
    if _trusted_follow_up(context_resolution):
        return "trusted_follow_up"
    return str(context_resolution["status"])


def _validated_inputs(
    target_country_names: Iterable[str], authorized_policy_market: str | None, rrf_k: int, current_order_weight: float
) -> tuple[str, set[str]]:
    if not isinstance(rrf_k, int) or rrf_k < 1:
        raise ValueError("rrf_k must be a positive integer")
    if not isinstance(current_order_weight, (int, float)) or isinstance(current_order_weight, bool) or current_order_weight < 0:
        raise ValueError("current_order_weight must be non-negative")
    targets = {_normalized(value) for value in target_country_names}
    targets.discard("")
    return (authorized_policy_market or "").upper(), targets


def _collect_evidence(
    searches: Sequence[Mapping[str, Any]], authorized_market: str, rrf_k: int
) -> tuple[dict[str, float], dict[str, DocumentIdentity], dict[str, Mapping[str, Any]], set[str]]:
    evidence: dict[str, float] = {}
    identities: dict[str, DocumentIdentity] = {}
    hits: dict[str, Mapping[str, Any]] = {}
    rejected_policy: set[str] = set()
    for search in searches:
        if not isinstance(search, Mapping):
            raise ValueError("search must be a mapping")
        weight = search.get("weight", 1.0)
        if not isinstance(weight, (int, float)) or isinstance(weight, bool) or weight < 0:
            raise ValueError("search weight must be non-negative")
        ranked_hits = search.get("hits")
        if not isinstance(ranked_hits, Sequence) or isinstance(ranked_hits, (str, bytes)):
            raise ValueError("search hits must be a sequence")
        seen: set[str] = set()
        for rank, raw_hit in enumerate(ranked_hits, start=1):
            if not isinstance(raw_hit, Mapping):
                raise ValueError("hit must be a mapping")
            identity = _identity(raw_hit)
            existing = identities.get(identity.public_id)
            if existing is not None and existing != identity:
                raise ValueError("conflicting identities for one public document id")
            identities.setdefault(identity.public_id, identity)
            hits.setdefault(identity.public_id, raw_hit)
            if not _eligible(identity, authorized_market or None):
                rejected_policy.add(identity.public_id)
                continue
            if identity.public_id not in seen:
                seen.add(identity.public_id)
                evidence[identity.public_id] = evidence.get(identity.public_id, 0.0) + float(weight) / (rrf_k + rank)
    return evidence, identities, hits, rejected_policy


def _stable_current(current_order: Sequence[str], evidence: Mapping[str, float]) -> list[str]:
    current: list[str] = []
    seen: set[str] = set()
    for raw_identifier in current_order:
        identifier = str(raw_identifier)
        if identifier in evidence and identifier not in seen:
            seen.add(identifier)
            current.append(identifier)
    return current


def _protected_global(
    intent_status: str,
    identities: Mapping[str, DocumentIdentity],
    evidence: Mapping[str, float],
    hits: Mapping[str, Mapping[str, Any]],
    targets: set[str],
    current_rank: Mapping[str, int],
    score,
) -> list[str]:
    if intent_status != "directory_compatible":
        return []
    matches = [
        identifier
        for identifier, identity in identities.items()
        if identifier in evidence
        and _is_global(identity)
        and _normalized(_metadata(hits[identifier]).get("record_country")) in targets
    ]
    matches.sort(key=lambda identifier: (current_rank.get(identifier, len(current_rank) + 1), -score(identifier), identifier))
    return matches[:1]


def fuse(
    searches: Sequence[Mapping[str, Any]],
    current_order: Sequence[str],
    *,
    target_country_names: Iterable[str] = (),
    runtime_scope_intent: Mapping[str, Any] | None = None,
    scope_intent: Mapping[str, Any] | None = None,
    authorized_policy_market: str | None = None,
    context_resolution: Mapping[str, Any] | None = None,
    rrf_k: int = 60,
    current_order_weight: float = 4.0,
) -> FusionResult:
    """Fuse trusted, in-scope candidates without inferring authorization.

    A global row is protected only for trusted runtime directory or
    international-sponsoring intent. At most one matching record can be
    protected. Country-policy rows must match the authorized policy market.
    Conflicting source/version/hash/section identities for one public ID fail.
    """
    if runtime_scope_intent is not None and scope_intent is not None:
        raise ValueError("supply only runtime_scope_intent")
    runtime_scope_intent = runtime_scope_intent if runtime_scope_intent is not None else scope_intent
    runtime_scope_intent, authorized_policy_market, context_resolution = validate_capture_provenance(
        runtime_scope_intent, authorized_policy_market, context_resolution,
    )
    authorized_market, targets = _validated_inputs(target_country_names, authorized_policy_market, rrf_k, current_order_weight)
    evidence, identities, hits, rejected_policy = _collect_evidence(searches, authorized_market, rrf_k)
    normalized_current = _stable_current(current_order, evidence)
    seen_current = set(normalized_current)
    current_rank = {identifier: rank for rank, identifier in enumerate(normalized_current, start=1)}
    context_status = _context_status(context_resolution)
    intent_status = _scope_intent_status(runtime_scope_intent)

    def score(identifier: str) -> float:
        rank = current_rank.get(identifier)
        continuity = 0.0 if rank is None else float(current_order_weight) / (rrf_k + rank)
        return evidence[identifier] + continuity

    if _trusted_follow_up(context_resolution):
        restored = [*normalized_current]
        restored.extend(identifier for identifier in sorted(evidence, key=lambda item: (-score(item), item)) if identifier not in seen_current)
        return FusionResult(
            order=tuple(restored),
            scores=tuple((identifier, score(identifier)) for identifier in restored),
            protected_global_ids=(),
            rejected_policy_ids=tuple(sorted(rejected_policy)),
            used_follow_up_fallback=True,
            context_status=context_status,
            scope_intent_status=intent_status,
        )

    protected = _protected_global(intent_status, identities, evidence, hits, targets, current_rank, score)
    protected_set = set(protected)
    remaining = [identifier for identifier in evidence if identifier not in protected_set]
    remaining.sort(key=lambda identifier: (-score(identifier), identifier))
    order = tuple([*protected, *remaining])
    return FusionResult(
        order=order,
        scores=tuple((identifier, score(identifier)) for identifier in order),
        protected_global_ids=tuple(protected),
        rejected_policy_ids=tuple(sorted(rejected_policy)),
        used_follow_up_fallback=False,
        context_status=context_status,
        scope_intent_status=intent_status,
    )
