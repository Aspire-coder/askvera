"""Render captured answers without claiming automated correctness scores."""
import argparse
import csv
import json
from pathlib import Path
import statistics


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def describe(row):
    if row is None:
        return 'NOT RUN'
    if row.get('error'):
        return 'ERROR: ' + row['error']
    response = row['response']
    metadata = response.get('metadata', {})
    return str(metadata.get('failure_layer') or ('fallback' if metadata.get('fallback') else 'answer returned'))


def comparison_basis(folder):
    path = folder / 'current-manifest.json'
    manifest = load(path) if path.exists() else {}
    if manifest.get('scoped_writer_comparison'):
        return ('Both arms use structural selection and bound-evidence approval in the same working tree. '
                'Only Fixed passes the reviewed draft to a scope-constrained final writer. '
                'Neither arm is deployed production; answer delivery is not a correctness score.')
    if manifest.get('review_only_comparison'):
        return ('Both arms use the same working-tree code and structural selector. Current keeps lexical-only '
                'approval; Fixed adds a separate bound-evidence semantic review for confidence-gate rejections. '
                'Neither arm is deployed production. See manifests and raw reviews; approval is experimental.')
    if manifest.get('comparison_basis') == 'same working-tree code, selector-only candidate':
        return ('Both arms use the same uncommitted local code. Current is the existing local selector; '
                'Fixed is the isolated structural selector with diagnostic-only set confidence. '
                'This is NOT a verified deployed-production baseline. See manifests for hashes and settings.')
    return ('Current code: archived commit ' + str(manifest.get('revision', 'UNVERIFIED'))
            + ' run locally. Fixed code: uncommitted local source. See manifests; deployment parity is not established here.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    args = parser.parse_args()
    folder = args.folder
    cases = load(folder / 'cases.json')
    results = {}
    for side in ('current', 'fixed'):
        for path in folder.glob(f'{side}-[1-3]-*.json'):
            row = load(path)
            results[(side, row['repeat'], row['id'])] = row
    rows = []
    text = ['# Current vs Fixed: captured answers', '',
            'Local-code comparison using the same model, captured settings and publication registry. '
            'This is not a live-widget test or a complete release gate. '
            'Answer returned is not an automatic correctness PASS. Legal wording has not been approved by this test.', '',
            'Shared caches, database access and telemetry publishing were isolated. '
            'Local synthetic sessions substitute for login/consent integration. '
            'Model, retrieval, evidence, numeric, PII and configured generation-guardrail logic remain real.', '',
            comparison_basis(folder), '']
    for side in ('current', 'fixed'):
        group = [r for (s, _, _), r in results.items() if s == side]
        if group:
            times = [r['duration_ms']/1000 for r in group]
            text.append(f"- {side.title()}: {len(group)} captures; median {statistics.median(times):.2f}s; "
                        f"range {min(times):.2f}-{max(times):.2f}s; "
                        f"{sum(bool(r.get('error')) for r in group)} execution errors; "
                        f"{sum(bool(r.get('storage_violations')) for r in group)} storage-isolation violations.")
    text += ['', 'Latency includes fast refusals. Do not interpret overall median as speed improvement without comparing outcomes.', '']
    for case in cases:
        case_id, country, question = case[:3]
        language = case[3] if len(case) > 3 else 'en'
        text += [f'## {case_id} | selected market {country} | {language}', '', question, '']
        for repeat in (1, 2, 3):
            pair = {side: results.get((side, repeat, case_id)) for side in ('current', 'fixed')}
            if not any(pair.values()):
                continue
            record = dict(id=case_id, country=country, question=question, repeat=repeat)
            text += [f'### Repeat {repeat}', '']
            for side, row in pair.items():
                response = row.get('response', {}) if row else {}
                answer = response.get('answer', '')
                citations = response.get('citations', [])
                duration = row['duration_ms']/1000 if row else ''
                status = describe(row)
                record.update({f'{side}_answer': answer, f'{side}_status': status,
                               f'{side}_seconds': duration, f'{side}_citations': json.dumps(citations, ensure_ascii=False),
                               f'{side}_review': ''})
                text += [f'**{side.title()}** | {duration}s | {status}', '', answer or '(No answer captured)', '',
                         'Citations: ' + json.dumps(citations, ensure_ascii=False), '']
            rows.append(record)
    with (folder / 'ANSWERS_SIDE_BY_SIDE.md').open('x', encoding='utf-8') as handle:
        handle.write('\n'.join(text))
    with (folder / 'ANSWERS_SIDE_BY_SIDE.csv').open('x', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f'Rendered {len(rows)} matched question/repeat rows; review columns intentionally blank.')


if __name__ == '__main__':
    main()
