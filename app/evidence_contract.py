"""Structured evidence contract for policy-grounded model answers.

The model is a writer, not a source of policy truth.  When enabled, this
module requires it to identify the approved retrieval sections supporting its
answer before the answer can be released to the user.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.retrieval.models import RetrievedDocument


@dataclass(frozen=True)
class EvidenceContractResult:
    """A parsed, validated model answer tied to approved evidence."""

    valid: bool
    answer: str = ""
    evidence_ids: tuple[str, ...] = ()
    reason: str = ""


def parse_evidence_contract(text: str, documents: list[RetrievedDocument]) -> EvidenceContractResult:
    """Validate a compact JSON answer against the retrieval evidence supplied."""
    payload = _parse_json_object(text)
    if payload is None:
        return EvidenceContractResult(False, reason="invalid_json")

    status = str(payload.get("status") or "").strip().lower()
    answer = str(payload.get("answer") or "").strip()
    if status != "approved" or not answer:
        return EvidenceContractResult(False, reason="answer_not_approved")

    allowed_ids = {document.id for document in documents if document.id}
    evidence_ids = _string_ids(payload.get("evidence_ids"))
    if not evidence_ids:
        return EvidenceContractResult(False, reason="missing_evidence_ids")
    if not set(evidence_ids).issubset(allowed_ids):
        return EvidenceContractResult(False, reason="unknown_evidence_id")

    claims = payload.get("claims")
    if not isinstance(claims, list) or not claims:
        return EvidenceContractResult(False, reason="missing_claims")
    for claim in claims:
        if not isinstance(claim, dict):
            return EvidenceContractResult(False, reason="invalid_claim")
        claim_text = str(claim.get("text") or "").strip()
        claim_evidence_ids = _string_ids(claim.get("evidence_ids"))
        if not claim_text or not claim_evidence_ids:
            return EvidenceContractResult(False, reason="claim_missing_support")
        if not set(claim_evidence_ids).issubset(set(evidence_ids)):
            return EvidenceContractResult(False, reason="claim_uses_unlisted_evidence")

    return EvidenceContractResult(True, answer=answer, evidence_ids=tuple(evidence_ids))


def _parse_json_object(text: str) -> dict[str, Any] | None:
    """Accept a JSON object even when a provider adds a small amount of framing."""
    candidate = (text or "").strip()
    if not candidate:
        return None
    if not candidate.startswith("{"):
        start, end = candidate.find("{"), candidate.rfind("}")
        if start == -1 or end <= start:
            return None
        candidate = candidate[start : end + 1]
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _string_ids(value: object) -> list[str]:
    """Return unique non-empty evidence identifiers in their declared order."""
    if not isinstance(value, list):
        return []
    ids: list[str] = []
    for item in value:
        identifier = str(item or "").strip()
        if identifier and identifier not in ids:
            ids.append(identifier)
    return ids
