"""Tests for the model-to-evidence answer contract."""

import json

from app.evidence_contract import parse_evidence_contract
from app.retrieval.models import RetrievedDocument


def _document(identifier: str = "section-1") -> RetrievedDocument:
    return RetrievedDocument(
        id=identifier,
        title="Policy - Sec 1.01",
        content="An FBO is a Forever Business Owner.",
        source="s3://policy.pdf",
    )


def test_accepts_claims_backed_by_declared_approved_evidence() -> None:
    payload = {
        "status": "approved",
        "answer": "An FBO is a Forever Business Owner.",
        "evidence_ids": ["section-1"],
        "claims": [{"text": "An FBO is a Forever Business Owner.", "evidence_ids": ["section-1"]}],
    }

    result = parse_evidence_contract(json.dumps(payload), [_document()])

    assert result.valid is True
    assert result.answer == payload["answer"]
    assert result.evidence_ids == ("section-1",)


def test_rejects_claims_that_reference_unknown_evidence() -> None:
    payload = {
        "status": "approved",
        "answer": "An FBO is a Forever Business Owner.",
        "evidence_ids": ["section-1"],
        "claims": [{"text": "An FBO is a Forever Business Owner.", "evidence_ids": ["made-up-section"]}],
    }

    result = parse_evidence_contract(json.dumps(payload), [_document()])

    assert result.valid is False
    assert result.reason == "claim_uses_unlisted_evidence"


def test_rejects_plain_text_when_contract_is_required() -> None:
    result = parse_evidence_contract("An FBO is a Forever Business Owner.", [_document()])

    assert result.valid is False
    assert result.reason == "invalid_json"
