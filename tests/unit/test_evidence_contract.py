"""Tests for the model-to-evidence answer contract."""

import json
import pytest

from app.evidence_contract import (  # noqa: F401
    MIN_CHECKED_CONTENT_TOKENS,
    _content_tokens,
    _uncovered_sentence,
)
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


def test_rejects_an_answer_carrying_a_sentence_no_claim_supports() -> None:
    """The reported gap: the contract only checked one direction.

    Every listed claim had to appear in the answer, but nothing stopped the
    answer carrying extra material no claim covered. A model could list one
    accurate, well-supported definition and append an unsupported sentence
    beside it, and the pair was accepted.
    """
    payload = {
        "status": "approved",
        "answer": (
            "An FBO is a Forever Business Owner. "
            "Joining today guarantees you a six figure annual income within twelve months."
        ),
        "evidence_ids": ["section-1"],
        "claims": [{"text": "An FBO is a Forever Business Owner.", "evidence_ids": ["section-1"]}],
        "coverage": {"complete": True, "omitted_material_facts": []},
    }

    result = parse_evidence_contract(json.dumps(payload), [_document()])

    assert result.valid is False
    assert result.reason == "answer_contains_unsupported_claim"


def test_accepts_prose_that_rephrases_and_joins_its_claims() -> None:
    """Demanding exact reuse of claim text would reject sound answers."""
    payload = {
        "status": "approved",
        "answer": (
            "An FBO is a Forever Business Owner. "
            "A Forever Business Owner orders directly from the Company."
        ),
        "evidence_ids": ["section-1"],
        "claims": [
            {"text": "An FBO is a Forever Business Owner.", "evidence_ids": ["section-1"]},
            {
                "text": "A Forever Business Owner orders directly from the Company.",
                "evidence_ids": ["section-1"],
            },
        ],
        "coverage": {"complete": True, "omitted_material_facts": []},
    }

    result = parse_evidence_contract(json.dumps(payload), [_document()])

    assert result.valid is True, result.reason


def test_markdown_scaffolding_is_not_treated_as_an_unsupported_claim() -> None:
    """A heading or bullet marker asserts nothing and must not fail the answer."""
    payload = {
        "status": "approved",
        "answer": "# Definition\n\n- \n\nAn FBO is a Forever Business Owner.",
        "evidence_ids": ["section-1"],
        "claims": [{"text": "An FBO is a Forever Business Owner.", "evidence_ids": ["section-1"]}],
        "coverage": {"complete": True, "omitted_material_facts": []},
    }

    result = parse_evidence_contract(json.dumps(payload), [_document()])

    assert result.valid is True, result.reason


def test_a_short_connective_sentence_is_not_judged_on_overlap() -> None:
    """Too little content to assert anything; scoring it produces noise."""
    payload = {
        "status": "approved",
        "answer": "An FBO is a Forever Business Owner. This is important.",
        "evidence_ids": ["section-1"],
        "claims": [{"text": "An FBO is a Forever Business Owner.", "evidence_ids": ["section-1"]}],
        "coverage": {"complete": True, "omitted_material_facts": []},
    }

    result = parse_evidence_contract(json.dumps(payload), [_document()])

    assert result.valid is True, result.reason


def test_an_invented_figure_beside_a_supported_claim_is_rejected() -> None:
    """Numbers are kept as tokens however short, so a fabricated figure shows."""
    payload = {
        "status": "approved",
        "answer": (
            "An FBO is a Forever Business Owner. "
            "Every FBO receives 47 percent commission on all retail orders placed."
        ),
        "evidence_ids": ["section-1"],
        "claims": [{"text": "An FBO is a Forever Business Owner.", "evidence_ids": ["section-1"]}],
        "coverage": {"complete": True, "omitted_material_facts": []},
    }

    result = parse_evidence_contract(json.dumps(payload), [_document()])

    assert result.valid is False
    assert result.reason == "answer_contains_unsupported_claim"


def test_a_short_assertion_bypasses_coverage_entirely() -> None:
    """Known gap, pinned so it cannot change without someone deciding to.

    Coverage skips any sentence with fewer than MIN_CHECKED_CONTENT_TOKENS
    content tokens, on the grounds that "This applies to all FBOs." asserts too
    little to score by overlap. The rationale is sound; the consequence is not
    symmetric. Skipping means accepting, and the shortest sentences include the
    most dangerous ones: "Income is guaranteed." carries two content tokens.

    This is a component-level gap, not a live one. EVIDENCE_GATED_OUTPUT_ENABLED
    defaults to false and production does not override it, so the contract does
    not run at all today; and income claims are separately routed to reviewed
    refusal copy. It matters when the flag is turned on.

    Closing it means either scoring short sentences strictly - which risks
    rejecting ordinary short replies such as "Yes, you can." - or judging
    materiality, which needs a false-rejection measurement first. Until that
    exists, the behaviour is recorded rather than quietly changed.
    """
    claims = [{"text": "FBO means Forever Business Owner."}]
    answer = "FBO means Forever Business Owner. Income is guaranteed."

    assert _uncovered_sentence(answer, claims) == ""
    assert len(_content_tokens("Income is guaranteed.")) < MIN_CHECKED_CONTENT_TOKENS

    # A longer unsupported claim is still caught, so the gap is specifically
    # about length rather than coverage being broken.
    assert _uncovered_sentence(
        "FBO means Forever Business Owner. You will earn 5000 EUR every month.", claims
    ) != ""
