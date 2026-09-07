"""Offline diagnostics against a superset of captured hits, not an approval gate."""
import argparse
import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.validation.validators.numeric_grounding_validator import (  # noqa: E402
    unsupported_numeric_claims, remove_unsupported_numeric_sentences,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    args = parser.parse_args()
    row = json.loads(args.capture.read_text(encoding='utf-8'))
    answer = [c['output_text'] for c in row['model_calls'] if c['operation'] == 'Converse'][-1]
    sources = {hit['_id']: hit['_source'] for search in row['searches']
               for hit in search.get('hits', {}).get('hits', []) if hit['_source'].get('content')}
    documents = [SimpleNamespace(content=s['content']) for s in sources.values()]
    claims = unsupported_numeric_claims(answer, documents)
    repaired, removed = remove_unsupported_numeric_sentences(answer, documents)
    print(json.dumps({'limit': 'All captured hits, not only approved evidence; raw output before cleanup',
                      'unsupported': [{'number': c.number, 'sentence': c.sentence, 'prefix': c.prefix} for c in claims],
                      'removed': removed, 'repaired': repaired}, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
