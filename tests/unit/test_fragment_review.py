"""Synthetic coverage checks; not proof of semantic segmentation quality."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from app.retrieval.source_binding import EvidenceSource
from scripts.final_claim_review import accepted_fragment_review, claim_output_config, review_final_answer


def example():
    parts = [{'text': text, 'supported': True, 'necessary': True, 'reason': 'Requested'}
             for text in ('Qualify with 4 credits.', 'Bonuses are conditional.')]
    return {'claims': [{'index': 0, 'parts': parts}], 'complete': True, 'safe': True}, [
        {'text': 'Qualify with 4 credits. Bonuses are conditional.'}]


def test_every_fragment_must_pass():
    review, claims = example()
    assert accepted_fragment_review(review, claims)
    review['claims'][0]['parts'][1]['necessary'] = False
    assert not accepted_fragment_review(review, claims)


@pytest.mark.parametrize('mutation', ['omit', 'reorder', 'rewrite', 'duplicate', 'empty', 'type', 'index', 'flag'])
def test_fragments_cannot_hide_or_change_original_text(mutation):
    review, claims = example()
    parts = review['claims'][0]['parts']
    if mutation == 'omit':
        parts.pop()
    elif mutation == 'reorder':
        parts.reverse()
    elif mutation == 'rewrite':
        parts[0]['text'] = 'Qualify with 2 credits.'
    elif mutation == 'duplicate':
        parts.append(deepcopy(parts[0]))
    elif mutation == 'empty':
        parts[0]['text'] = ''
    elif mutation == 'type':
        parts[0]['text'] = 4
    elif mutation == 'index':
        review['claims'][0]['index'] = True
    else:
        parts[0]['necessary'] = 'true'
    with pytest.raises(ValueError):
        accepted_fragment_review(review, claims)


def test_whitespace_only_variation_does_not_change_coverage():
    review, claims = example()
    review['claims'][0]['parts'][0]['text'] = 'Qualify\nwith 4 credits.'
    assert accepted_fragment_review(review, claims)


def test_schema_generation_does_not_mutate_baseline():
    before = claim_output_config()
    assert 'parts' in json.loads(claim_output_config(True)['textFormat']['structure']['jsonSchema']['schema'])[
        'properties']['claims']['items']['properties']
    assert claim_output_config() == before


def test_fragment_request_uses_one_bounded_call_and_exact_claims():
    review, claims = example()
    source = EvidenceSource('test', 'v1', 'rule', 'CA', claims[0]['text'])
    claims[0]['support'] = [{'source_id': source.binding_id, 'quote': source.content}]
    payload = {'answer': source.content, 'claims': claims}
    calls = []

    def converse(**kwargs):
        calls.append(kwargs)
        return {'stopReason': 'end_turn', 'output': {'message': {'content': [{'text': json.dumps(review)}]}}}

    result = review_final_answer(SimpleNamespace(converse=converse), 'model', 'Rules and bonuses?', 'CA', 'en',
                                 payload, [source], per_claim=True, structured_output=True, fragment_review=True)
    assert result['passed']
    assert len(calls) == 1
    assert calls[0]['inferenceConfig'] == {'maxTokens': 768}
    assert result['request']['claims'] == claims


def test_fragment_review_rejects_non_structured_mode_before_model():
    with pytest.raises(ValueError, match='requires structured'):
        review_final_answer(None, 'model', 'Question?', 'CA', 'en', {}, [], fragment_review=True)
