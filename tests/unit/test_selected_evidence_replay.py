import pytest
from scripts.replay_selected_evidence import selected_documents


def capture(ids, sources):
    return {'response': {'metadata': {'retrieval': {'evidence_decision': {
        'approved': True, 'evidence_ids': ids}}}},
        'searches': [{'hits': {'hits': [{'_source': source} for source in sources]}}]}


def test_selection_excludes_extra_hits_and_preserves_citation_order():
    row = capture(['b', 'a'], [{'id': key, 'content': key, 'source_uri': key} for key in ['a', 'extra', 'b']])
    assert [doc.id for doc in selected_documents(row)] == ['b', 'a']


@pytest.mark.parametrize('ids,sources', [
    ([], []), (['missing'], []),
    (['a'], [{'id': 'a', 'content': 'old'}, {'id': 'a', 'content': 'new'}]),
])
def test_unreconstructable_evidence_is_not_guessed(ids, sources):
    with pytest.raises(ValueError):
        selected_documents(capture(ids, sources))


def test_generation_capture_survives_refused_response_without_metadata():
    doc = {'id': 'approved', 'title': 'Policy', 'content': 'Exact enriched text', 'source': 's3://kb/policy'}
    row = {'response': {'metadata': {}}, 'generation_inputs': [{'retrieval_result': {'documents': [doc]}}]}
    assert selected_documents(row)[0].content == 'Exact enriched text'


def test_multiple_generations_are_not_silently_mismatched():
    with pytest.raises(ValueError, match='Multiple generations'):
        selected_documents({'generation_inputs': [{}, {}]})
