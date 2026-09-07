"""Offline citation/numeric replay using only recorded approved evidence, in order.

Not a full orchestrator, governance, retrieval, or answer-correctness gate.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.retrieval.models import RetrievedDocument  # noqa: E402
from app.validation.validators.numeric_grounding_validator import (  # noqa: E402
    remove_unsupported_numeric_sentences, unsupported_numeric_claims,
)
from utils.inline_citations import separate_verified_citations  # noqa: E402


def selected_documents(row):
    inputs = row.get('generation_inputs', [])
    if inputs:
        if len(inputs) != 1:
            raise ValueError('Multiple generations require explicit output/evidence pairing')
        documents = inputs[0]['retrieval_result']['documents']
        if not documents:
            raise ValueError('No generation evidence recorded')
        return [RetrievedDocument(**doc) for doc in documents]
    metadata = row.get('response', {}).get('metadata', {})
    decision = metadata.get('retrieval', {}).get('evidence_decision') or metadata.get('evidence_decision', {})
    ids = decision.get('evidence_ids', [])
    if not decision.get('approved') or not ids:
        raise ValueError('No recorded approved evidence IDs; cannot reconstruct selection')
    sources = {}
    for search in row.get('searches', []):
        for hit in search.get('hits', {}).get('hits', []):
            source = hit.get('_source', {})
            key = source.get('id')
            if key not in ids:
                continue
            if key in sources and any(sources[key].get(field) != source.get(field)
                                      for field in ('content', 'source_uri', 'ingestion_id')):
                raise ValueError('Conflicting captured versions for selected evidence')
            sources[key] = source
    if any(key not in sources or not sources[key].get('content') for key in ids):
        raise ValueError('Selected evidence missing from captured hits')
    return [RetrievedDocument(
        id=key, title=sources[key].get('source_file', ''), content=sources[key]['content'],
        source=sources[key].get('source_uri', ''), page=str(sources[key].get('start_page', '')),
        country=sources[key].get('country', ''), language=sources[key].get('language', ''),
        metadata={**sources[key].get('metadata', {}), 'section_id': sources[key].get('section_id', '')},
    ) for key in ids]


def replay(row):
    result = {'id': row.get('id'), 'repeat': row.get('repeat'), 'question': row.get('question')}
    try:
        documents = selected_documents(row)
        calls = [call for call in row.get('model_calls', []) if call.get('operation') == 'Converse']
        if not calls or not calls[-1].get('output_text'):
            raise ValueError('No captured model output')
        raw = calls[-1]['output_text']
        cleaned = separate_verified_citations(raw, documents)
        repaired, removed = remove_unsupported_numeric_sentences(cleaned, documents)
        result.update(status='replayed', evidence_ids=[doc.id for doc in documents], raw_answer=raw,
                      after_citation_cleanup=cleaned, after_numeric_repair=repaired, removed=removed,
                      remaining_unsupported=[claim.number for claim in unsupported_numeric_claims(repaired, documents)])
    except ValueError as exc:
        result.update(status='skipped', reason=str(exc))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    results = [replay(json.loads(path.read_text(encoding='utf-8')))
               for path in sorted(args.folder.glob('fixed-[123]-*.json'))]
    report = {'scope': __doc__, 'results': results}
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    print(json.dumps({'replayed': sum(row['status'] == 'replayed' for row in results),
                      'skipped': sum(row['status'] == 'skipped' for row in results)}))


if __name__ == '__main__':
    main()
