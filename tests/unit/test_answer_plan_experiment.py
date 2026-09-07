from copy import deepcopy
import json
from unittest.mock import Mock

import pytest

from app.retrieval.source_binding import EvidenceSource
from scripts.answer_plan_experiment import compare, validate_plan


SOURCE = EvidenceSource('policy', 'generation', 'rule', 'CA', 'Four credits during this month.')
QUESTION = 'How do I qualify this month?'
POINT = {'question_span': 'qualify this month', 'text': 'Four credits during this month.',
         'support': [{'source_id': SOURCE.binding_id, 'quote': SOURCE.content}]}


def response(payload):
    return {'stopReason': 'end_turn', 'output': {'message': {'content': [{'text': json.dumps(payload)}]}}}


@pytest.mark.parametrize('change', ['span', 'quote', 'source', 'empty', 'extra', 'text', 'too_many'])
def test_rejects_invalid_plan(change):
    plan = {'points': [deepcopy(POINT)]}
    if change == 'span':
        plan['points'][0]['question_span'] = 'unasked bonus'
    elif change == 'quote':
        plan['points'][0]['support'][0]['quote'] = 'Two credits'
    elif change == 'source':
        plan['points'][0]['support'][0]['source_id'] = 'other'
    elif change == 'empty':
        plan['points'] = []
    elif change == 'extra':
        plan['approved'] = True
    elif change == 'text':
        plan['points'][0]['text'] = None
    else:
        plan['points'] *= 13
    with pytest.raises(ValueError):
        validate_plan(plan, QUESTION, [SOURCE])


def test_plan_binding_does_not_prove_truth():
    point = deepcopy(POINT)
    point['text'] = 'An unsupported interpretation'
    assert validate_plan({'points': [point]}, QUESTION, [SOURCE])  # structural only


def test_bad_plan_blocks_writer():
    client = Mock(converse=Mock(return_value=response({'points': []})))
    result = compare(client, 'model', QUESTION, 'en', [SOURCE], planned=True)
    assert result['error'] and 'writer' not in result
    assert client.converse.call_count == 1


def test_plan_is_data_full_passage_retained():
    answer = {'answer': POINT['text'], 'claims': [{'text': POINT['text'], 'support': POINT['support']}]}
    client = Mock(converse=Mock(side_effect=[response({'points': [POINT]}), response(answer)]))
    result = compare(client, 'model', QUESTION, 'en', [SOURCE], planned=True)
    assert result['binding_valid']
    assert client.converse.call_count == 2
    data = json.loads(client.converse.call_args.kwargs['messages'][0]['content'][0]['text'])
    assert data['answer_plan'] == {'points': [POINT]}
    assert data['passages'][0]['content'] == SOURCE.content
    assert 'approved' not in result


def test_direct_control_has_no_plan():
    answer = {'answer': POINT['text'], 'claims': [{'text': POINT['text'], 'support': POINT['support']}]}
    client = Mock(converse=Mock(return_value=response(answer)))
    assert compare(client, 'model', QUESTION, 'en', [SOURCE], planned=False)['binding_valid']
    assert client.converse.call_count == 1
    data = json.loads(client.converse.call_args.kwargs['messages'][0]['content'][0]['text'])
    assert 'answer_plan' not in data


def test_invalid_final_claim_never_repaired():
    client = Mock(converse=Mock(return_value=response({'answer': 'Extra', 'claims': []})))
    result = compare(client, 'model', QUESTION, 'en', [SOURCE], planned=False)
    assert not result['binding_valid'] and result['error']


def test_segments_writer_uses_one_call_and_assembles_exact_text():
    segments = {'segments': [{'text': POINT['text'], 'support': POINT['support']}]}
    client = Mock(converse=Mock(return_value=response(segments)))
    result = compare(client, 'model', QUESTION, 'en', [SOURCE], planned=False, segments_only=True)
    assert result['binding_valid'] and result['assembled_answer'] == POINT['text']
    assert client.converse.call_count == 1 and 'plan' not in result
    config = client.converse.call_args.kwargs['outputConfig']
    schema = json.loads(config['textFormat']['structure']['jsonSchema']['schema'])
    assert set(schema['properties']) == {'segments'}


def test_segments_does_not_repair_old_dual_text_payload():
    client = Mock(converse=Mock(return_value=response({'answer': 'old', 'claims': []})))
    result = compare(client, 'model', QUESTION, 'en', [SOURCE], planned=False, segments_only=True)
    assert not result['binding_valid'] and 'assembled_answer' not in result


def test_no_bundled_planning_and_segments_experiment():
    client = Mock()
    with pytest.raises(ValueError):
        compare(client, 'model', QUESTION, 'en', [SOURCE], planned=True, segments_only=True)
    client.converse.assert_not_called()
