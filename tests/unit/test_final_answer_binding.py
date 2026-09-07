"""Synthetic contract tests, not real company-policy gold answers."""
from copy import deepcopy
from dataclasses import replace

import pytest

from app.final_answer_binding import bind_final_answer
from app.retrieval.source_binding import EvidenceSource


def example():
    sources = [EvidenceSource('test-policy', 'v1', 'activity', 'CA', 'Qualify each month with 4 credits.'),
               EvidenceSource('test-policy', 'v1', 'rank', 'CA', 'Rank retention is separate from monthly activity.')]
    claims = [{'text': source.content, 'support': [{'source_id': source.binding_id, 'quote': source.content}]}
              for source in sources]
    return {'answer': '\n\n'.join(claim['text'] for claim in claims), 'claims': claims}, sources


def test_each_claim_keeps_its_own_source_not_just_first_citation():
    payload, sources = example()
    result = bind_final_answer(payload, sources)
    assert result.answer == payload['answer']
    assert result.source_ids == tuple(source.binding_id for source in sources)
    assert result.claims[1].support[0][0] == sources[1].binding_id


@pytest.mark.parametrize('change', ['append', 'omit_claim', 'reorder', 'change_number', 'repeat_claim'])
def test_unlisted_or_changed_answer_text_rejected(change):
    payload, sources = example()
    if change == 'append':
        payload['answer'] += ' You also receive extra bonuses.'
    elif change == 'omit_claim':
        payload['claims'].pop()
    elif change == 'reorder':
        payload['claims'].reverse()
    elif change == 'change_number':
        payload['answer'] = payload['answer'].replace('4', '2')
    else:
        payload['claims'].append(deepcopy(payload['claims'][0]))
    with pytest.raises(ValueError, match='differs'):
        bind_final_answer(payload, sources)


def test_correct_quote_on_wrong_passage_rejected():
    payload, sources = example()
    payload['claims'][0]['support'][0]['source_id'] = sources[1].binding_id
    with pytest.raises(ValueError, match='does not belong'):
        bind_final_answer(payload, sources)


@pytest.mark.parametrize('field,value', [('country', 'BE'), ('generation_id', 'v2'),
                                         ('content', 'Qualify with 2 credits.')])
def test_stale_or_swapped_source_rejected(field, value):
    payload, sources = example()
    sources[0] = replace(sources[0], **{field: value})
    with pytest.raises(ValueError, match='Unknown or stale'):
        bind_final_answer(payload, sources)


def test_whitespace_changes_are_allowed_without_changing_language_or_facts():
    source = EvidenceSource('test-de', 'v1', 'activity', 'DE', 'Sie benötigen 4 persönliche Credits.')
    payload = {'answer': 'Sie benötigen\n4 persönliche Credits.', 'claims': [
        {'text': 'Sie benötigen 4 persönliche Credits.', 'support': [
            {'source_id': source.binding_id, 'quote': 'Sie benötigen 4 persönliche\nCredits.'}]}]}
    assert bind_final_answer(payload, [source]).answer == payload['answer']


def test_text_binding_does_not_claim_semantic_approval():
    payload, sources = example()
    payload['claims'][0]['text'] = 'You never need to qualify.'
    payload['answer'] = ' '.join(claim['text'] for claim in payload['claims'])
    result = bind_final_answer(payload, sources)
    # Exact quote membership cannot detect this contradiction. A semantic gate
    # is required; the binding result intentionally has no approved property.
    assert not hasattr(result, 'approved')


@pytest.mark.parametrize('bad', [
    None, {}, {'answer': 3, 'claims': []}, {'answer': 'x', 'claims': []},
    {'answer': 'x', 'claims': [None]}, {'answer': 'x' * 8001, 'claims': []},
])
def test_malformed_contract_rejected(bad):
    _, sources = example()
    with pytest.raises(ValueError):
        bind_final_answer(bad, sources)
