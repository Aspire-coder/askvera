"""Tests for the model-to-evidence answer contract."""

import json
import pytest

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
        "coverage": {"complete": True, "omitted_material_facts": []},
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
        "coverage": {"complete": True, "omitted_material_facts": []},
    }

    result = parse_evidence_contract(json.dumps(payload), [_document()])

    assert result.valid is False
    assert result.reason == "claim_uses_unlisted_evidence"


def test_rejects_plain_text_when_contract_is_required() -> None:
    result = parse_evidence_contract("An FBO is a Forever Business Owner.", [_document()])

    assert result.valid is False
    assert result.reason == "invalid_json"


def test_rejects_answer_when_material_evidence_was_omitted() -> None:
    payload = {
        "status": "approved",
        "answer": "One of the qualification requirements is shown.",
        "evidence_ids": ["section-1"],
        "claims": [{"text": "One requirement.", "evidence_ids": ["section-1"]}],
        "coverage": {"complete": False, "omitted_material_facts": ["alternative threshold"]},
    }

    result = parse_evidence_contract(json.dumps(payload), [_document()])

    assert result.valid is False
    assert result.reason == "incomplete_answer"


@pytest.mark.parametrize('field,value,reason', [
    ('answer', 123, 'invalid_answer_type'),
    ('claim', 123, 'invalid_claim_text_type'),
    ('claim', 'A completely different answer.', 'claim_not_in_answer'),
    ('ids', ['section-1', 123], 'missing_evidence_ids'),
])
def test_rejects_malformed_or_detached_claims(field, value, reason):
    payload = {'status': 'approved', 'answer': 'An FBO is a Forever Business Owner.',
               'evidence_ids': ['section-1'],
               'claims': [{'text': 'An FBO is a Forever Business Owner.', 'evidence_ids': ['section-1']}],
               'coverage': {'complete': True, 'omitted_material_facts': []}}
    if field == 'claim':
        payload['claims'][0]['text'] = value
    else:
        payload['evidence_ids' if field == 'ids' else field] = value
    result = parse_evidence_contract(json.dumps(payload), [_document()])
    assert not result.valid and result.reason == reason


def test_claim_matching_preserves_multilingual_text_and_allows_whitespace():
    payload = {'status': 'approved', 'answer': 'Sie benötigen\n4 Case-Credits.',
               'evidence_ids': ['section-1'],
               'claims': [{'text': 'Sie benötigen 4 Case-Credits.', 'evidence_ids': ['section-1']}],
               'coverage': {'complete': True, 'omitted_material_facts': []}}
    assert parse_evidence_contract(json.dumps(payload), [_document()]).valid
