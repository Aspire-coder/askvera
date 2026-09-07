from copy import deepcopy
from dataclasses import replace
from unittest.mock import Mock

import pytest

from app.final_answer_binding import assemble_bound_segments
from app.retrieval.source_binding import EvidenceSource
from scripts.conversation_comparison import ConversationRunError, compare_conversation


def example():
    source = EvidenceSource('synthetic-policy', 'v1', 'monthly', 'CA', 'Four credits this month.')
    segment = {'text': 'You need four credits this month.',
               'support': [{'source_id': source.binding_id, 'quote': source.content}]}
    return {'segments': [segment]}, [source]


def test_single_text_is_displayed_exactly_and_keeps_its_support():
    payload, sources = example()
    payload['segments'].append(deepcopy(payload['segments'][0]))
    payload['segments'][1]['text'] = 'These credits must be from the current month.'
    original = deepcopy(payload)
    result = assemble_bound_segments(payload, sources)
    assert result.answer == ' '.join(s['text'] for s in payload['segments'])
    assert [c.text for c in result.claims] == [s['text'] for s in payload['segments']]
    assert result.source_ids == (sources[0].binding_id,)
    assert payload == original
    payload['segments'][0]['text'] = 'Later mutation'
    assert 'Later mutation' not in result.answer


@pytest.mark.parametrize('bad', [
    None, {}, {'segments': []}, {'segments': [None]},
    {'segments': [{'text': '', 'support': []}]},
    {'segments': [{'text': 7, 'support': []}]},
    {'segments': [{'text': 'x', 'support': []}]},
    {'answer': 'Do not silently drop me', 'segments': []},
])
def test_bad_segments_rejected(bad):
    with pytest.raises(ValueError):
        assemble_bound_segments(bad, example()[1])


@pytest.mark.parametrize('change', ['quote', 'generation', 'too_long', 'too_many'])
def test_boundaries_preserved(change):
    payload, sources = example()
    if change == 'quote':
        payload['segments'][0]['support'][0]['quote'] = 'Invented quote'
    elif change == 'generation':
        sources = [replace(sources[0], generation_id='v2')]
    elif change == 'too_long':
        payload['segments'] *= 2
        payload['segments'][0]['text'] = 'x' * 4001
    else:
        payload['segments'] *= 25
    with pytest.raises(ValueError):
        assemble_bound_segments(payload, sources)


def test_no_semantic_or_safety_approval_claim():
    payload, sources = example()
    payload['segments'][0]['text'] = 'An unsupported interpretation.'
    result = assemble_bound_segments(payload, sources)
    assert not hasattr(result, 'approved')  # Membership is not entailment.


def sequence():
    return {'id': 'followups', 'turns': [
        {'message': 'Belgium sponsoring?', 'country': 'US', 'language': 'en', 'expected': 'global only'},
        {'message': 'What about Germany?', 'country': 'US', 'language': 'en', 'expected': 'new target'},
        {'message': 'Und meine Landesrichtlinie?', 'country': 'DE', 'language': 'de', 'expected': 'explicit market change'},
    ]}


def test_separate_complete_histories_and_explicit_market_changes():
    adapters = {arm: Mock(side_effect=[{'answer': f'{arm} {i}', 'citations': []} for i in range(3)])
                for arm in ('current', 'candidate')}
    result = compare_conversation(sequence(), adapters)
    for arm, adapter in adapters.items():
        assert adapter.call_args_list[0].kwargs['history'] == []
        assert adapter.call_args_list[1].kwargs['history'][0]['answer'] == f'{arm} 0'
        last = adapter.call_args_list[2].kwargs
        assert last['request']['country'] == 'DE' and last['request']['language'] == 'de'
        assert len(last['history']) == 2
        assert 'expected' not in last['request']  # Gold behavior never sent to bot.
        assert result[arm][2]['grade'] == 'not_reviewed'
        assert len(result[arm]) == 3


def test_adapter_cannot_mutate_history_or_other_arm():
    def mutate(request, history):
        request['country'] = 'BE'
        history.clear()
        return {'answer': 'Delivered clarification'}
    other = Mock(return_value={'answer': 'Delivered refusal'})
    result = compare_conversation(sequence(), {'current': mutate, 'candidate': other})
    assert len(result['current'][2]['history']) == 2
    assert result['current'][0]['request']['country'] == 'US'
    assert other.call_args_list[1].kwargs['history'][0]['answer'] == 'Delivered refusal'


def test_draft_only_is_not_a_delivered_turn():
    with pytest.raises(ConversationRunError) as caught:
        compare_conversation(sequence(), {'current': Mock(return_value={'draft': 'Rejected text'}),
                                          'candidate': Mock()})
    record = caught.value.records['current'][0]
    assert record['grade'] == 'execution_error' and 'response' not in record


def test_malformed_later_turn_is_rejected_before_any_calls():
    data = sequence()
    data['turns'][2]['message'] = ''
    adapters = {'current': Mock(), 'candidate': Mock()}
    with pytest.raises(ValueError):
        compare_conversation(data, adapters)
    for adapter in adapters.values():
        adapter.assert_not_called()


def test_completed_turns_survive_later_failure():
    adapters = {'current': Mock(side_effect=[{'answer': 'Delivered'}, TimeoutError()]),
                'candidate': Mock(return_value={'answer': 'Other delivered'})}
    with pytest.raises(ConversationRunError) as caught:
        compare_conversation(sequence(), adapters)
    records = caught.value.records
    assert records['current'][0]['response']['answer'] == 'Delivered'
    assert records['candidate'][0]['response']['answer'] == 'Other delivered'
    assert records['current'][1]['history'][0]['answer'] == 'Delivered'
    assert records['current'][1]['error_type'] == 'TimeoutError'


def test_fresh_sequence_has_no_previous_history():
    adapters = {arm: Mock(return_value={'answer': 'Delivered'}) for arm in ('current', 'candidate')}
    compare_conversation(sequence(), adapters)
    compare_conversation(sequence(), adapters)
    for adapter in adapters.values():
        assert adapter.call_args_list[3].kwargs['history'] == []
