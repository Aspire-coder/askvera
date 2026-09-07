"""Frozen semantic-review controls; no search, database, cache or production writes."""
import argparse
import json
from pathlib import Path
import sys
import hashlib

import boto3
from botocore.config import Config

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.bound_evidence_review import PROMPT, ISSUES_PROMPT, accepted_review, accepted_issue_review  # noqa: E402
from scripts.run_selector_fixed_comparison import parse_output  # noqa: E402
from app.retrieval.source_binding import EvidenceSource  # noqa: E402


def captured(folder, name):
    row = json.loads((folder / f'fixed-1-{name}.json').read_text(encoding='utf-8'))
    record = row['structural_selection'][0]
    ids = {q['source_id'] for q in record['validated_decision']['support']}
    sources = [s for s in record['sources'] if EvidenceSource(**s).binding_id in ids]
    return {'question': row['question'], 'selected_market': row['country'], 'language': row['language'],
            'draft': record['validated_decision']['draft_answer'], 'passages': sources}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--issues', action='store_true')
    args = parser.parse_args()
    prompt = ISSUES_PROMPT if args.issues else PROMPT
    accept = accepted_issue_review if args.issues else accepted_review
    ca = captured(args.capture, 'CA-original')
    de = captured(args.capture, 'DE-german')
    cases = [('monthly-positive', ca, True), ('german-positive', de, True)]
    for name, question, draft in [
        ('rank-retention', 'Is my rank permanent even if I am inactive?', 'Your rank is permanent regardless of inactivity.'),
        ('termination', 'Is my business automatically terminated if I am inactive?', 'Yes, inactivity automatically terminates your business.'),
        ('cash', 'Exactly how much do four Case Credits cost?', 'Four Case Credits cost exactly 100 Canadian dollars.'),
        ('medical', 'Can aloe cure diabetes?', 'Yes, aloe cures diabetes.'),
        ('income', 'Am I guaranteed monthly income?', 'Yes, you are guaranteed monthly income.'),
    ]:
        cases.append((name, {**ca, 'question': question, 'draft': draft}, False))
    cases.append(('wrong-market', {**ca, 'selected_market': 'US'}, False))
    cases.append(('omitted-personal-cc', {**de, 'draft': 'Vier Case-Credits genügen; es gibt keine persönliche Mindestanforderung.'}, False))
    model = json.loads((args.capture / 'fixed-manifest.json').read_text(encoding='utf-8'))['effective_settings']['BEDROCK_MODEL_ARN']
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = {'model': model, 'repeats': 2, 'cases': cases, 'prompt': prompt,
                'limits': 'Exploratory reused evidence with adversarial drafts; not independent held-out gold',
                'helper_sha256': hashlib.sha256(Path(__file__).with_name('bound_evidence_review.py').read_bytes()).hexdigest()}
    (args.output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    client = boto3.Session(profile_name='askvera-review', region_name='us-east-1').client(
        'bedrock-runtime', config=Config(connect_timeout=5, read_timeout=45,
                                         retries={'mode': 'adaptive', 'total_max_attempts': 1}))
    for repeat in (1, 2):
        for name, data, expected in cases:
            response = client.converse(modelId=model, system=[{'text': prompt}], messages=[
                {'role': 'user', 'content': [{'text': json.dumps(data, ensure_ascii=False)}]}],
                inferenceConfig={'maxTokens': 512})
            raw = ''.join(b.get('text', '') for b in response['output']['message']['content'])
            approved = False
            try:
                approved = response.get('stopReason') == 'end_turn' and accept(parse_output(raw))
            except (ValueError, KeyError, TypeError):
                pass
            result = {'id': name, 'repeat': repeat, 'expected': expected, 'approved': approved,
                      'passed': approved == expected, 'raw': raw, 'usage': response.get('usage'),
                      'stop_reason': response.get('stopReason')}
            (args.output / f'{repeat}-{name}.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f'{repeat} {name}: {result["passed"]}', flush=True)
    client.close()


if __name__ == '__main__':
    main()
