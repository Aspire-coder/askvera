"""Convert the reviewed scenario table to a test fixture without altering questions."""
import json
from pathlib import Path
import re


def main():
    root = Path(__file__).resolve().parents[1]
    audit = root / 'docs/audits/2026-09-05'
    source = audit / 'MARKET_POLICY_CUSTOMER_SCENARIOS.md'
    cases = []
    for line in source.read_text(encoding='utf-8').splitlines():
        if not re.match(r'^\| (BE|NL|CA|DE|IT|SE|UK|US)-\d{2} \|', line):
            continue
        identifier, market, question, expected = [v.strip() for v in line.strip('|').split('|')]
        cases.append(dict(id=identifier, country='GB' if market == 'UK' else market,
                          language={'DE': 'de', 'IT': 'it'}.get(market, 'en'),
                          question=question, expected_behavior=expected))
    assert len(cases) == 40 and len({c['id'] for c in cases}) == 40
    with (audit / 'market-policy-cases.json').open('x', encoding='utf-8') as stream:
        json.dump({'source': str(source), 'cases': cases}, stream, ensure_ascii=False, indent=2)
    print('Prepared 40 unique cases; expected behavior is not sent to the model.')


if __name__ == '__main__':
    main()
