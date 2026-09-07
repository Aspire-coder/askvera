"""Publish complete captured answers; never equate capture success with correctness."""
import json
from pathlib import Path
import statistics


def main():
    audit = Path(__file__).resolve().parents[1] / 'docs/audits/2026-09-05'
    output = audit / 'market-policy-full-01'
    fixture = json.loads((audit / 'market-policy-cases.json').read_text(encoding='utf-8'))['cases']
    rows = []
    lines = ['# Current: 40 market-policy questions and complete answers', '',
             'One run per question. Local archive of deployed commit 7d29dad, live AWS retrieval/model calls, '
             'synthetic sessions and bypassed shared caches. Not browser/HTTP verification. '
             'Capture success is NOT a correctness score.', '',
             'Raw per-case JSON includes retrieved search results, generation evidence, model calls and traces.', '']
    for case in fixture:
        path = output / f"current-1-{case['id']}.json"
        if not path.exists():
            raise RuntimeError(f"Missing capture: {case['id']}")
        row = json.loads(path.read_text(encoding='utf-8'))
        rows.append(row)
        response = row.get('response', {})
        lines += [f"## {case['id']} | {case['country']} | {case['language']}", '',
                  '**Question:** ' + case['question'], '',
                  '**Expected behavior:** ' + case['expected_behavior'], '',
                  f"**Recorded duration:** {row['duration_ms']/1000:.2f} seconds. "
                  f"**Capture error:** {row.get('error', 'None')}. "
                  f"**Cache:** {response.get('metadata', {}).get('cache', 'unavailable')}.", '',
                  '### Full answer', '', response.get('answer', '(No answer captured)'), '', '### Citations', '']
        for citation in response.get('citations', []):
            lines += [f"- {citation.get('title', '')}; page {citation.get('page', '')}; "
                      f"section {citation.get('section', '')}; version {citation.get('documentVersion', '')}; "
                      f"source: {citation.get('uri', '')}"]
        if not response.get('citations'):
            lines += ['No citations returned.']
        lines += ['']
    durations = [r['duration_ms']/1000 for r in rows]
    summary = dict(cases=len(rows), capture_errors=sum('error' in r for r in rows),
                   storage_violations=sum(len(r['storage_violations']) for r in rows),
                   median_seconds=statistics.median(durations), maximum_seconds=max(durations),
                   correctness='Requires case-by-case evidence review; not inferred from answer delivery')
    with (output / 'ANSWERS.md').open('x', encoding='utf-8') as stream:
        stream.write('\n'.join(lines))
    with (output / 'capture-summary.json').open('x', encoding='utf-8') as stream:
        json.dump(summary, stream, indent=2)
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
