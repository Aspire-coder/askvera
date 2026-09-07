"""Two-repeat, source-blind relevance experiment. Not an answer approval gate."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import boto3
from botocore.config import Config

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.relevance_review import PROMPT, output_config, review_relevance  # noqa: E402
from scripts.run_final_claim_controls import cases_from_capture, extended_controls  # noqa: E402


def controls(folder):
    base, sources = cases_from_capture(folder)
    question = 'What must I do to be Active this month in my Home Operating Company?'
    extended = extended_controls(folder, [(n, p, e, question) for n, p, e in base], sources)
    result = []
    for name, payload, _, query, _, language, _ in extended:
        # These are RELEVANCE labels, intentionally different from answer correctness.
        result.append({'id': name, 'question': query, 'answer': payload['answer'], 'language': language,
                       'expected_relevant': name not in {'mixed-claim', 'mixed-separated'},
                       'label_scope': 'relevance only; does not assert factual validity or safety'})
    monthly = base[0][1]['answer']
    result.extend([
        {'id': 'unasked-medical', 'question': question,
         'answer': monthly + ' Forever products cure diabetes.', 'language': 'en', 'expected_relevant': False},
        {'id': 'friendly-monthly', 'question': question,
         'answer': 'Happy to help. ' + monthly, 'language': 'en', 'expected_relevant': True},
        {'id': 'unasked-weather', 'question': question,
         'answer': monthly + ' The weather is sunny today.', 'language': 'en', 'expected_relevant': False},
    ])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    cases = controls(args.capture)
    model = json.loads((args.capture / 'fixed-manifest.json').read_text(encoding='utf-8'))['effective_settings']['BEDROCK_MODEL_ARN']
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = {'scope': 'Exploratory relevance-only controls, not held-out or release validation',
                'model': model, 'repeats': 2, 'cases': cases, 'prompt': PROMPT, 'output_config': output_config(),
                'code_sha256': {n: hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest()
                                for n in ('relevance_review.py', 'run_relevance_controls.py', 'run_final_claim_controls.py')},
                'capture_sha256': {n: hashlib.sha256((args.capture / n).read_bytes()).hexdigest()
                                   for n in ('fixed-1-CA-paraphrase.json', 'fixed-1-DE-german.json', 'fixed-manifest.json')}}
    (args.output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    client = boto3.Session(profile_name='askvera-review', region_name='us-east-1').client(
        'bedrock-runtime', config=Config(connect_timeout=5, read_timeout=45,
                                         retries={'mode': 'adaptive', 'total_max_attempts': 1}))
    try:
        for repeat in (1, 2):
            for case in cases:
                result = review_relevance(client, model, case['question'], case['answer'], case['language'])
                result.update(id=case['id'], repeat=repeat, expected_relevant=case['expected_relevant'],
                              matches_expected=not result.get('error') and
                              result['relevance_passed'] == case['expected_relevant'])
                with (args.output / f'{repeat}-{case["id"]}.json').open('x', encoding='utf-8') as stream:
                    json.dump(result, stream, ensure_ascii=False, indent=2)
                print(f'{repeat} {case["id"]}: {result["matches_expected"]}', flush=True)
    finally:
        client.close()


if __name__ == '__main__':
    main()
