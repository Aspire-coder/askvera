from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.evidence_contract import parse_evidence_contract
from app.prompts.templates import EVIDENCE_CONTRACT_PROMPT
from app.retrieval.source_binding import EvidenceSource
from scripts.run_matched_chat_comparison import evaluation_turns
from scripts.segments_chat_adapter import bridge, generate


def sample():
    source = EvidenceSource('policy', 'active', 'monthly', 'CA', 'Four credits this month.')
    payload = {'status': 'approved', 'segments': [{'text': 'Four credits this month.', 'support': [
        {'source_id': source.binding_id, 'quote': source.content}]}],
        'coverage': {'complete': True, 'omitted_material_facts': []}}
    return source, payload, [SimpleNamespace(id='doc-1')]


def test_bridge_uses_exact_text_and_maps_to_original_document_id():
    source, payload, docs = sample()
    result = bridge(payload, [source], docs)
    assert result['answer'] == payload['segments'][0]['text']
    assert result['claims'] == [{'text': result['answer'], 'evidence_ids': ['doc-1']}]
    assert parse_evidence_contract(json.dumps(result), docs).valid


@pytest.mark.parametrize('change', [
    {'status': 'insufficient_evidence'}, {'answer': 'independent text'},
    {'coverage': {'complete': False, 'omitted_material_facts': []}},
    {'coverage': {'complete': True, 'omitted_material_facts': ['personal credit']}},
    {'coverage': {'complete': 'true', 'omitted_material_facts': []}},
])
def test_bridge_never_invents_coverage_or_accepts_dual_text(change):
    source, payload, docs = sample()
    with pytest.raises(ValueError):
        bridge({**payload, **change}, [source], docs)


def test_wrong_quote_not_relocated():
    source, payload, docs = sample()
    payload['segments'][0]['support'][0]['quote'] = 'Five credits'
    with pytest.raises(ValueError):
        bridge(payload, [source], docs)


@pytest.mark.parametrize('stop', ['end_turn', 'guardrail_intervened', 'max_tokens'])
def test_hook_keeps_provider_request_guards_and_restores_client(monkeypatch, stop):
    from dataclasses import dataclass, field

    @dataclass
    class Prompt:
        system_prompt: str = EVIDENCE_CONTRACT_PROMPT.strip()
        user_prompt: str = 'history and latest question'
        country: str = 'CA'
        language: str = 'en'
        metadata: dict = field(default_factory=lambda: {'evidence_contract': True})

    source, payload, docs = sample()
    monkeypatch.setattr('scripts.segments_chat_adapter.document_sources', lambda *a, **k: [source])
    raw = {'stopReason': stop, 'output': {'message': {'content': [{'text': json.dumps(payload)}]}}}
    calls = []

    def converse(**kwargs):
        calls.append(kwargs)
        return deepcopy(raw)

    client = SimpleNamespace(converse=converse)

    def provider(prompt, result, correlation):
        assert 'history and latest question' in prompt.user_prompt
        assert EVIDENCE_CONTRACT_PROMPT.strip() not in prompt.system_prompt
        return client.converse(modelId='same-model', guardrailConfig={'guardrailVersion': '1'},
                               inferenceConfig={'maxTokens': 1000})

    records = []
    answer = generate(provider, client, Prompt(), SimpleNamespace(documents=docs), 'c', lambda *a: {'active'}, records)
    assert len(calls) == 1
    schema = json.loads(calls[0].pop('outputConfig')['textFormat']['structure']['jsonSchema']['schema'])
    assert set(schema['required']) == {'status', 'segments', 'coverage'}
    assert schema['additionalProperties'] is False
    assert calls == [{'modelId': 'same-model', 'guardrailConfig': {'guardrailVersion': '1'},
                      'inferenceConfig': {'maxTokens': 1000}}]
    assert client.converse is converse
    assert records[0]['structurally_valid'] is (stop == 'end_turn')
    if stop != 'end_turn':
        assert answer == raw


def test_followup_fixture_keeps_all_21_turns_in_order():
    args = SimpleNamespace(conversation_fixture=Path('tests/fixtures/followup_conversations.json'), limit=40)
    turns = evaluation_turns(args)
    assert len(turns) == 21
    assert len({t['sequence_id'] for t in turns}) == 7
    for offset in range(0, 21, 3):
        group = turns[offset:offset+3]
        assert [t['turn'] for t in group] == [1, 2, 3]
        assert len({t['sequence_id'] for t in group}) == 1
    assert turns[12]['country'] == 'DE' and turns[14]['country'] == 'CA'


def test_noncontract_path_is_explicitly_unchanged():
    from unittest.mock import Mock
    original = Mock(return_value='existing clarification')
    active_ids = Mock(side_effect=AssertionError('Must not resolve sources for this path'))
    prompt = SimpleNamespace(metadata={'evidence_contract': False})
    records = []
    assert generate(original, None, prompt, None, 'c', active_ids, records) == 'existing clarification'
    original.assert_called_once_with(prompt, None, 'c')
    assert records == [{'not_applicable': 'Existing non-policy output path; unchanged'}]
