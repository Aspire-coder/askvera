import json
from unittest.mock import Mock

import pytest

from scripts.relevance_review import review_relevance, validate_review
from scripts.run_relevance_controls import controls


def client_for(review, stop='end_turn'):
    return Mock(converse=Mock(return_value={
        'output': {'message': {'content': [{'text': json.dumps(review)}]}}, 'stopReason': stop}))


def test_only_visible_input_no_approval():
    client = client_for({'relevant': True, 'unnecessary_spans': [], 'reason': 'Requested'})
    result = review_relevance(client, 'model', 'Question?', 'Answer.', 'en')
    request = json.loads(client.converse.call_args.kwargs['messages'][0]['content'][0]['text'])
    assert request == {'question': 'Question?', 'answer': 'Answer.', 'language': 'en'}
    assert result['relevance_passed'] is True
    assert 'passed' not in result and 'approved' not in result
    assert client.converse.call_count == 1
    assert client.converse.call_args.kwargs['inferenceConfig']['maxTokens'] == 768


@pytest.mark.parametrize('review', [
    {'relevant': 'true', 'unnecessary_spans': [], 'reason': 'x'},
    {'relevant': True, 'unnecessary_spans': ['extra'], 'reason': 'x'},
    {'relevant': False, 'unnecessary_spans': [], 'reason': 'x'},
    {'relevant': False, 'unnecessary_spans': ['invented'], 'reason': 'x'},
    {'relevant': False, 'unnecessary_spans': [' '], 'reason': 'x'},
    {'relevant': True, 'unnecessary_spans': [], 'reason': ''},
    {'relevant': True, 'unnecessary_spans': [], 'reason': 'x', 'approved': True},
    [],
])
def test_invalid_reviews_fail_closed(review):
    result = review_relevance(client_for(review), 'model', 'Q?', 'Answer extra', 'en')
    assert result['relevance_passed'] is False
    assert result['error']


def test_valid_negative():
    assert validate_review({'relevant': False, 'unnecessary_spans': ['extra'], 'reason': 'Unasked'},
                           'Answer extra') is False


def test_truncation_never_passes():
    result = review_relevance(client_for({'relevant': True, 'unnecessary_spans': [], 'reason': 'x'}, 'max_tokens'),
                              'model', 'Q?', 'Answer', 'en')
    assert result['error'] and not result['relevance_passed']


@pytest.mark.parametrize('answer', ['', 'x' * 8001, None])
def test_input_bound_before_model(answer):
    client = Mock()
    with pytest.raises(ValueError):
        review_relevance(client, 'model', 'Q?', answer, 'en')
    client.converse.assert_not_called()


def test_control_labels_and_grouping(monkeypatch):
    # No dependency on uncommitted cloud artifacts or AWS access in unit tests.
    monkeypatch.setattr('scripts.run_relevance_controls.cases_from_capture',
                        lambda folder: ([('monthly-rule', {'answer': 'Monthly rule'}, True)], []))
    names = ('mixed-claim', 'mixed-separated', 'mixed-requested', 'mixed-requested-separated',
             'medical-addition', 'DE-missing-personal', 'DE-wrong-number', 'wrong-passage')
    monkeypatch.setattr('scripts.run_relevance_controls.extended_controls',
                        lambda *args: [(name, {'answer': 'Same displayed text'}, False, 'Q?', 'CA', 'en', [])
                                       for name in names])
    cases = {case['id']: case for case in controls(None)}
    for left, right in [('mixed-claim', 'mixed-separated'), ('mixed-requested', 'mixed-requested-separated')]:
        for key in ('question', 'answer', 'language', 'expected_relevant'):
            assert cases[left][key] == cases[right][key]
    for name in ('medical-addition', 'DE-missing-personal', 'DE-wrong-number', 'wrong-passage'):
        assert cases[name]['expected_relevant'] is True  # NOT an answer approval
    assert not cases['mixed-claim']['expected_relevant']
    assert cases['mixed-requested']['expected_relevant']
