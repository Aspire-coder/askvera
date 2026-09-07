"""Offline presentation replay. Does not verify claim entailment or run the chatbot."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.response import ResponseBuilder  # noqa: E402
from app.retrieval.models import RetrievalResult  # noqa: E402
from scripts.replay_selected_evidence import selected_documents  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    rows = []
    for path in sorted(args.folder.glob('fixed-1-*.json')):
        row = json.loads(path.read_text(encoding='utf-8'))
        if not row.get('generation_inputs'):
            continue
        documents = selected_documents(row)
        captured = row['generation_inputs'][0]['retrieval_result']
        result = RetrievalResult(documents, [doc.to_source() for doc in documents], captured['confidence'],
                                 metadata=captured.get('metadata', {}))
        calls = [call for call in row['model_calls'] if call.get('operation') == 'Converse']
        raw = calls[-1]['output_text']
        citations = ResponseBuilder()._supporting_citations(raw, result)
        rows.append({'id': row['id'], 'captured_citations': row['response']['citations'],
                     'replayed_citations': citations})
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump({'scope': __doc__, 'rows': rows}, stream, ensure_ascii=False, indent=2)
    print(json.dumps([{'id': row['id'], 'before': len(row['captured_citations']),
                       'after': len(row['replayed_citations'])} for row in rows]))


if __name__ == '__main__':
    main()
