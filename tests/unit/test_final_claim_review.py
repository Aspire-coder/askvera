import json
from types import SimpleNamespace

import pytest

from app.retrieval.source_binding import EvidenceSource
from scripts.final_claim_review import accepted_claim_review, review_final_answer


def fixture():
    source = EvidenceSource('test', 'v1', 'monthly', 'CA', 'Qualify each month.')
    payload = {'answer': source.content, 'claims': [{'text': source.content, 'support': [
        {'source_id': source.binding_id, 'quote': source.content}]}]}
    return source, payload


@pytest.mark.parametrize('raw,stop,expected', [
    ('{"issues":[]}', 'end_turn', True),
    ('{"issues":[{"kind":"wrong_scope","detail":"Unasked bonus detail"}]}', 'end_turn', False),
    ('{"issues":[]} trailing text', 'end_turn', False),
    ('{"issues":[]}', 'max_tokens', False),
    ('{"issues":false}', 'end_turn', False),
    ('```json\n{"issues":[]}\n```', 'end_turn', True),
    ('```json\n{"issues":[]}\n``` trailing', 'end_turn', False),
    ('```json\n{"issues":[]}', 'end_turn', False),
])
def test_only_complete_strict_review_passes(raw, stop, expected):
    source, payload = fixture()
    calls = []

    def converse(**kwargs):
        calls.append(kwargs)
        return {'stopReason': stop, 'output': {'message': {'content': [{'text': raw}]}}}

    record = review_final_answer(SimpleNamespace(converse=converse), 'model', 'When do I qualify?',
                                 'CA', 'en', payload, [source])
    assert record['passed'] is expected
    assert len(calls) == 1
    assert calls[0]['inferenceConfig']['maxTokens'] == 768
    assert 'outputConfig' not in calls[0]
    data = json.loads(calls[0]['messages'][0]['content'][0]['text'])
    assert data['claims'][0]['support'][0]['source_id'] == data['passages'][0]['source_id']


def test_unbound_answer_never_calls_model():
    source, payload = fixture()
    payload['answer'] += ' Extra claim.'
    with pytest.raises(ValueError, match='differs'):
        review_final_answer(None, 'model', 'When?', 'CA', 'en', payload, [source])


def judgment():
    return {'claims': [{'index': 0, 'supported': True, 'necessary': True, 'reason': 'Direct answer'}],
            'complete': True, 'safe': True}


@pytest.mark.parametrize('field', ['supported', 'necessary'])
def test_each_claim_dimension_can_independently_reject(field):
    review = judgment()
    assert accepted_claim_review(review, 1)
    review['claims'][0][field] = False
    assert not accepted_claim_review(review, 1)


@pytest.mark.parametrize('field,value', [('index', True), ('index', 1), ('index', '0'),
                                         ('supported', 'true'), ('necessary', 1),
                                         ('reason', ''), ('reason', None)])
def test_claim_schema_is_strict(field, value):
    review = judgment()
    review['claims'][0][field] = value
    with pytest.raises(ValueError):
        accepted_claim_review(review, 1)


@pytest.mark.parametrize('claims', [[], None, [judgment()['claims'][0]] * 2])
def test_missing_or_extra_claims_rejected(claims):
    review = judgment()
    review['claims'] = claims
    with pytest.raises(ValueError):
        accepted_claim_review(review, 1)


def test_duplicate_indexes_rejected_even_with_right_count():
    review = judgment()
    review['claims'] *= 2
    with pytest.raises(ValueError, match='indexes'):
        accepted_claim_review(review, 2)


@pytest.mark.parametrize('field', ['complete', 'safe'])
def test_whole_answer_flags_remain_required(field):
    review = judgment()
    review[field] = False
    assert not accepted_claim_review(review, 1)
    review[field] = 'false'
    with pytest.raises(ValueError):
        accepted_claim_review(review, 1)


def test_per_claim_request_and_response_contract():
    source, payload = fixture()
    calls = []

    def converse(**kwargs):
        calls.append(kwargs)
        return {'stopReason': 'end_turn', 'output': {'message': {'content': [
            {'text': json.dumps(judgment())}]}}}

    result = review_final_answer(SimpleNamespace(converse=converse), 'model', 'When?', 'CA', 'en',
                                 payload, [source], per_claim=True)
    assert result['passed']
    assert 'necessary' in calls[0]['system'][0]['text']
    assert 'expected' not in result['request']
    assert result['request']['claims'] == payload['claims']


def test_old_review_schema_cannot_pass_new_protocol():
    source, payload = fixture()
    client = SimpleNamespace(converse=lambda **kwargs: {
        'stopReason': 'end_turn', 'output': {'message': {'content': [{'text': '{"issues":[]}'}]}}})
    result = review_final_answer(client, 'model', 'When?', 'CA', 'en', payload, [source], per_claim=True)
    assert not result['passed']
    assert result['error']


@pytest.mark.parametrize('variant', ['valid', 'unnecessary', 'trailing', 'truncated', 'missing-claim'])
def test_structured_output_still_requires_local_validation(variant):
    source, payload = fixture()
    review = judgment()
    if variant == 'unnecessary':
        review['claims'][0]['necessary'] = False
    if variant == 'missing-claim':
        review['claims'] = []
    calls = []

    def converse(**kwargs):
        calls.append(kwargs)
        raw = json.dumps(review) + (' Extra explanation' if variant == 'trailing' else '')
        return {'stopReason': 'max_tokens' if variant == 'truncated' else 'end_turn',
                'output': {'message': {'content': [{'text': raw}]}}}

    result = review_final_answer(SimpleNamespace(converse=converse), 'model', 'When?', 'CA', 'en',
                                 payload, [source], per_claim=True, structured_output=True)
    assert result['passed'] is (variant == 'valid')
    assert len(calls) == 1
    config = calls[0]['outputConfig']
    assert config == result['output_config']
    assert config['textFormat']['type'] == 'json_schema'
    schema = json.loads(config['textFormat']['structure']['jsonSchema']['schema'])
    assert schema['additionalProperties'] is False
    assert set(schema['required']) == {'claims', 'complete', 'safe'}
    assert schema['properties']['claims']['items']['additionalProperties'] is False
    assert result['elapsed_seconds'] >= 0


def test_structured_output_cannot_be_used_with_old_review():
    source, payload = fixture()
    with pytest.raises(ValueError, match='requires per-claim'):
        review_final_answer(None, 'model', 'When?', 'CA', 'en', payload, [source], structured_output=True)


def test_structured_api_failure_never_falls_back_to_unstructured():
    source, payload = fixture()
    calls = []

    def converse(**kwargs):
        calls.append(kwargs)
        raise RuntimeError('API unavailable')

    with pytest.raises(RuntimeError, match='unavailable'):
        review_final_answer(SimpleNamespace(converse=converse), 'model', 'When?', 'CA', 'en',
                            payload, [source], per_claim=True, structured_output=True)
    assert len(calls) == 1
