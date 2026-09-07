import hashlib
import json
from types import SimpleNamespace

import pytest

from app.retrieval.opensearch_sections import OpenSearchSectionProvider
from scripts.structural_chat_adapter import prepare, resolve, select
from scripts.selector_binding_adapter import source_alias
from scripts.run_matched_chat_comparison import validate_snapshot_coverage


def rows():
    text = 'To be considered Active, an FBO must qualify monthly.'
    return [({'id': 'one', 'country': 'CA', 'language': 'en', 'access_scope': 'country',
              'document_type': 'policy', 'section_id': '4.03', 'section_title': 'Activity Qualification',
              'source_uri': 's3://approved/canada.pdf', 'content': text,
              'metadata': {'ingestion_id': 'active', 'status': 'active',
                           'content_hash': hashlib.sha256(text.encode()).hexdigest()}}, 0.35)]


def prepared():
    return prepare(OpenSearchSectionProvider(), rows(), 'How do I become Active?', 'CA', 'en', {'active'}, 10)


def response(sources):
    return {'decision': 'ANSWER_FACT', 'draft_answer': 'Qualify monthly.', 'missing_facts': [], 'confidence': 0.99,
            'support': [{'source_id': source_alias(sources[0]), 'quote': sources[0].content}]}


def test_actual_sources_and_scores_preserved_without_confidence_promotion():
    request, pairs, documents, sources = prepared()
    assert sources[0].document_id == 's3://approved/canada.pdf'
    assert 'frozen-capture' not in json.dumps(request)
    selected, diagnostic = resolve(response(sources), pairs, documents, sources,
                                   question='How do I become Active?', country='CA', language='en', active_ids={'active'})
    assert selected == pairs
    assert selected[0][0] is pairs[0][0]
    assert selected[0][1] == 0.35
    assert not any(key.startswith('evidence_selector') for key in selected[0][0])
    assert diagnostic['confidence'] == 0.99


def test_abstention_has_no_unselected_fallback():
    _, pairs, documents, sources = prepared()
    payload = {'decision': 'INSUFFICIENT_EVIDENCE', 'draft_answer': '', 'support': [],
               'missing_facts': ['Requested field'], 'confidence': 0.1}
    selected, _ = resolve(payload, pairs, documents, sources, question='Unknown?', country='CA',
                          language='en', active_ids={'active'})
    assert selected == []


@pytest.mark.parametrize('stop,raw', [('max_tokens', '{}'), ('end_turn', '{}'), ('end_turn', 'not json')])
def test_invalid_or_incomplete_response_fails_closed(stop, raw):
    records = []
    client = SimpleNamespace(converse=lambda **kw: {'stopReason': stop,
                             'output': {'message': {'content': [{'text': raw}]}}})
    assert select(OpenSearchSectionProvider(), rows(), 'How do I become Active?', 'CA', 'en', {'active'},
                  10, client, 'test-model', records) == []
    assert records[0]['validation_error']


def test_invalid_source_never_invokes_model():
    def forbidden(**kwargs):
        pytest.fail('Must validate provenance before inference')
    records = []
    assert select(OpenSearchSectionProvider(), rows(), 'Active?', 'CA', 'en', {'stale'}, 10,
                  SimpleNamespace(converse=forbidden), 'test-model', records) == []


@pytest.mark.parametrize('fenced', [False, True])
def test_valid_response_plain_or_fenced(fenced):
    _, _, _, sources = prepared()
    raw = json.dumps(response(sources))
    if fenced:
        raw = '```json\n' + raw + '\n```'

    def converse(**kwargs):
        assert kwargs['inferenceConfig'] == {'maxTokens': 512}
        return {'stopReason': 'end_turn', 'output': {'message': {'content': [{'text': raw}]}}}
    records = []
    selected = select(OpenSearchSectionProvider(), rows(), 'How do I become Active?', 'CA', 'en', {'active'},
                      10, SimpleNamespace(converse=converse), 'test-model', records)
    assert selected == rows()
    assert records[0]['validated_decision']['decision'] == 'ANSWER_FACT'


def test_unknown_alias_rejected():
    _, pairs, documents, sources = prepared()
    payload = response(sources)
    payload['support'][0]['source_id'] = 'unknown'
    with pytest.raises(ValueError, match='Unknown'):
        resolve(payload, pairs, documents, sources, question='Active?', country='CA', language='en', active_ids={'active'})


def test_missing_snapshot_country_rejected_before_calls():
    with pytest.raises(ValueError, match='country missing'):
        validate_snapshot_coverage([('one', 'CA', 'Active?', 'en')], {
            'results': [{'complete': True, 'total': 1, 'generation': {'country': 'US'}}]})


def test_incomplete_snapshot_rejected():
    with pytest.raises(ValueError, match='Incomplete'):
        validate_snapshot_coverage([], {'results': [{'complete': False}]})
